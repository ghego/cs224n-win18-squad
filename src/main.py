# Copyright 2018 Stanford University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This file contains the entrypoint to the rest of the code"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import io
import json
import sys
import logging
import argparse

import tensorflow as tf

from qa_model import QAModel
from vocab import get_glove
from official_eval_helper import get_json_data, generate_answers


logging.basicConfig(level=logging.INFO)

MAIN_DIR = os.path.relpath(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # relative path of the main directory
DEFAULT_DATA_DIR = os.path.join(MAIN_DIR, "data")  # relative path of data dir
EXPERIMENTS_DIR = os.path.join(MAIN_DIR, "experiments")  # relative path of experiments dir


def initialize_model(session, model, train_dir, expect_exists):
    """
    Initializes model from train_dir.

    Inputs:
      session: TensorFlow session
      model: QAModel
      train_dir: path to directory where we'll look for checkpoint
      expect_exists: If True, throw an error if no checkpoint is found.
        If False, initialize fresh model if no checkpoint is found.
    """
    print("Looking for model at %s..." % train_dir)
    ckpt = tf.train.get_checkpoint_state(train_dir)
    v2_path = ckpt.model_checkpoint_path + ".index" if ckpt else ""
    if ckpt and (tf.gfile.Exists(ckpt.model_checkpoint_path) or tf.gfile.Exists(v2_path)):
        print("Reading model parameters from %s" % ckpt.model_checkpoint_path)
        model.saver.restore(session, ckpt.model_checkpoint_path)
    else:
        if expect_exists:
            raise Exception("There is no saved checkpoint at %s" % train_dir)
        else:
            print("There is no saved checkpoint at %s. Creating model with fresh parameters." % train_dir)
            session.run(tf.global_variables_initializer())
            print('Num params: %d' % sum(v.get_shape().num_elements() for v in tf.trainable_variables()))


def main(unused_argv):
    # Print an error message if you've entered flags incorrectly
    if len(unused_argv) != 1:
        raise Exception("There is a problem with how you entered flags: %s" % unused_argv)

    # Check for Python 3
    if sys.version_info[0] != 3:
        raise Exception("ERROR: You must use Python 2 but you are running Python %i" % sys.version_info[0])

    # Print out Tensorflow version
    print("This code was developed and tested on TensorFlow 1.8.0. Your TensorFlow version: %s" % tf.__version__)

    # Define train_dir
    if not FLAGS.experiment_name and not FLAGS.train_dir and FLAGS.mode != "official_eval":
        raise Exception("You need to specify either --experiment_name or --train_dir")
    FLAGS.train_dir = FLAGS.train_dir or os.path.join(EXPERIMENTS_DIR, FLAGS.experiment_name)

    # Initialize bestmodel directory
    bestmodel_dir = os.path.join(FLAGS.train_dir, "best_checkpoint")

    # Define path for glove vecs
    FLAGS.glove_path = FLAGS.glove_path or os.path.join(DEFAULT_DATA_DIR, "glove.6B.{}d.txt".format(FLAGS.embedding_size))

    # Load embedding matrix and vocab mappings
    emb_matrix, word2id, id2word = get_glove(FLAGS.glove_path, FLAGS.embedding_size)

    # Get filepaths to train/dev datafiles for tokenized queries, contexts and answers
    train_context_path = os.path.join(FLAGS.data_dir, "train.context")
    train_qn_path = os.path.join(FLAGS.data_dir, "train.question")
    train_ans_path = os.path.join(FLAGS.data_dir, "train.span")
    dev_context_path = os.path.join(FLAGS.data_dir, "dev.context")
    dev_qn_path = os.path.join(FLAGS.data_dir, "dev.question")
    dev_ans_path = os.path.join(FLAGS.data_dir, "dev.span")

    # Initialize model
    qa_model = QAModel(FLAGS, id2word, word2id, emb_matrix)

    # Some GPU settings
    config=tf.ConfigProto()
    config.gpu_options.allow_growth = True

    # Split by mode
    if FLAGS.mode == "train":

        # Setup train dir and logfile
        if not os.path.exists(FLAGS.train_dir):
            os.makedirs(FLAGS.train_dir)
        file_handler = logging.FileHandler(os.path.join(FLAGS.train_dir, "log.txt"))
        logging.getLogger().addHandler(file_handler)

        # Save a record of flags as a .json file in train_dir
        with open(os.path.join(FLAGS.train_dir, "flags.json"), 'w') as fout:
            json.dump(FLAGS.__dict__, fout)

        # Make bestmodel dir if necessary
        if not os.path.exists(bestmodel_dir):
            os.makedirs(bestmodel_dir)

        with tf.Session(config=config) as sess:

            # Load most recent model
            initialize_model(sess, qa_model, FLAGS.train_dir, expect_exists=False)

            # Train
            qa_model.train(sess, train_context_path, train_qn_path, train_ans_path, dev_qn_path, dev_context_path, dev_ans_path)


    elif FLAGS.mode == "show_examples":
        with tf.Session(config=config) as sess:

            # Load best model
            initialize_model(sess, qa_model, bestmodel_dir, expect_exists=True)

            # Show examples with F1/EM scores
            _, _ = qa_model.check_f1_em(sess, dev_context_path, dev_qn_path, dev_ans_path, "dev", num_samples=10, print_to_screen=True)


    elif FLAGS.mode == "official_eval":
        if FLAGS.json_in_path == "":
            raise Exception("For official_eval mode, you need to specify --json_in_path")
        if FLAGS.ckpt_load_dir == "":
            raise Exception("For official_eval mode, you need to specify --ckpt_load_dir")

        # Read the JSON data from file
        qn_uuid_data, context_token_data, qn_token_data = get_json_data(FLAGS.json_in_path)

        with tf.Session(config=config) as sess:

            # Load model from ckpt_load_dir
            initialize_model(sess, qa_model, FLAGS.ckpt_load_dir, expect_exists=True)

            # Get a predicted answer for each example in the data
            # Return a mapping answers_dict from uuid to answer
            answers_dict = generate_answers(sess, qa_model, word2id, qn_uuid_data, context_token_data, qn_token_data)

            # Write the uuid->answer mapping a to json file in root dir
            print("Writing predictions to %s..." % FLAGS.json_out_path)
            with io.open(FLAGS.json_out_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(answers_dict, ensure_ascii=False))
                print("Wrote predictions to %s" % FLAGS.json_out_path)


    else:
        raise Exception("Unexpected value of FLAGS.mode: %s" % FLAGS.mode)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # High-level options
    parser.add_argument(
        "--gpu",
        type=int,
        default=0,
        help="Which GPU to use, if you have multiple.")
    parser.add_argument(
        "--mode",
        type=str,
        default="train",
        help="Available modes: train / show_examples / official_eval")
    parser.add_argument(
        "--experiment_name",
        type=str,
        default="",
        help="Unique name for your experiment. This will create a directory by this name in the experiments/ directory, which will hold all data related to this experiment")
    parser.add_argument(
        "--num_epochs",
        type=int,
        default=0,
        help="Number of epochs to train. 0 means train indefinitely")

    # Hyperparameters
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=0.001,
        help="Learning rate.")
    parser.add_argument(
        "--max_gradient_norm",
        type=float,
        default=5.0,
        help="Clip gradients to this norm.")
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.15,
        help="Fraction of units randomly dropped on non-recurrent connections.")
    parser.add_argument(
        "--batch_size",
        type=int,
        default=100,
        help="Batch size to use")
    parser.add_argument(
        "--hidden_size",
        type=int,
        default=200,
        help="Size of the hidden states")
    parser.add_argument(
        "--context_len",
        type=int,
        default=600,
        help="The maximum context length of your model")
    parser.add_argument(
        "--question_len",
        type=int,
        default=30,
        help="The maximum question length of your model")
    parser.add_argument(
        "--embedding_size",
        type=int,
        default=100,
        help="Size of the pretrained word vectors. This needs to be one of the available GloVe dimensions: 50/100/200/300")

    # How often to print, save, eval
    parser.add_argument(
        "--print_every",
        type=int,
        default=1,
        help="How many iterations to do per print.")
    parser.add_argument(
        "--save_every",
        type=int,
        default=500,
        help="How many iterations to do per save.")
    parser.add_argument(
        "--eval_every",
        type=int,
        default=500,
        help="How many iterations to do per calculating loss/f1/em on dev set. Warning: this is fairly time-consuming so don't do it too often.")
    parser.add_argument(
        "--keep",
        type=int,
        default=1,
        help="How many checkpoints to keep. 0 indicates keep all (you shouldn't need to do keep all though - it's very storage intensive).")

    # Reading and saving data
    parser.add_argument(
        "--train_dir",
        type=str,
        default="",
        help="Training directory to save the model parameters and other info. Defaults to experiments/{experiment_name}")
    parser.add_argument(
        "--glove_path",
        type=str,
        default="",
        help="Path to glove .txt file. Defaults to data/glove.6B.{embedding_size}d.txt")
    parser.add_argument(
        "--data_dir",
        type=str,
        default=DEFAULT_DATA_DIR,
        help="Where to find preprocessed SQuAD data for training. Defaults to data/")
    parser.add_argument(
        "--ckpt_load_dir",
        type=str,
        default="",
        help="For official_eval mode, which directory to load the checkpoint fron. You need to specify this for official_eval mode.")
    parser.add_argument(
        "--json_in_path",
        type=str,
        default="",
        help="For official_eval mode, path to JSON input file. You need to specify this for official_eval_mode.")
    parser.add_argument(
        "--json_out_path",
        type=str,
        default="predictions.json",
        help="Output path for official_eval mode. Defaults to predictions.json")

    FLAGS, unparsed = parser.parse_known_args()

    os.environ["CUDA_VISIBLE_DEVICES"] = str(FLAGS.gpu)

    tf.app.run(main=main, argv=[sys.argv[0]] + unparsed)
