# cs224n-win18-squad
Code for the Default Final Project (SQuAD) for [CS224n](http://web.stanford.edu/class/cs224n/), Winter 2018

Note: this code is adapted in part from the [Neural Language Correction](https://github.com/stanfordmlgroup/nlc/) code by the Stanford Machine Learning Group.

- [Assignment pdf](./pdfs/default_project_v2.pdf)

# Getting Started

## Train baseline
To start training the baseline, run the following commands:
```
source squad/bin/activate # Remember to always activate your squad environment
cd src # Change to code directory
python main.py --experiment_name=baseline \
               --mode=train \
               --data_dir=/mnt/training/data/squad \
               --glove_path=/mnt/training/data/glove/glove.6B.100d.txt
```

## Tracking progress in TensorBoard
```
tensorboard --logdir=./experiments/
```
and remember to ssh with tunnelling on port 6006 (from your local machine).

## Inspecting Output
Once you have a trained model, you will want to see example output to help you begin to think
about error analysis, and how you might improve the model. Run the following command.
```
python main.py --experiment_name=baseline \
               --mode=show_examples \
               --data_dir=/mnt/training/data/squad \
               --glove_path=/mnt/training/data/glove/glove.6B.100d.txt
```

## Run official eval helper
```
python main.py --experiment_name=baseline \
               --mode=official_eval \
               --data_dir=/mnt/training/data/squad \
               --glove_path=/mnt/training/data/glove/glove.6B.100d.txt \
               --json_in_path=/mnt/training/data/squad/dev-v1.1.json \
               --ckpt_load_dir=../experiments/baseline/best_checkpoint/
```
