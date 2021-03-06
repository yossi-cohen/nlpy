#!env/bin/python
# coding: utf8
"""Example of training an additional entity type

This script shows how to add a new entity type to an existing pre-trained NER
model. To keep the example short and simple, only four sentences are provided
as examples. In practice, you'll need many more — a few hundred would be a
good start. You will also likely need to mix in examples of other entity
types, which might be obtained by running the entity recognizer over unlabelled
sentences, and adding their annotations to the training set.

The actual training is performed by looping over the examples, and calling
`nlp.entity.update()`. The `update()` method steps through the words of the
input. At each word, it makes a prediction. It then consults the annotations
provided on the GoldParse instance, to see whether it was right. If it was
wrong, it adjusts its weights so that the correct action will score higher
next time.

After training your model, you can save it to a directory. We recommend
wrapping models as Python packages, for ease of deployment.

For more details, see the documentation:
* Training: https://spacy.io/usage/training
* NER: https://spacy.io/usage/linguistic-features#named-entities

Compatible with: spaCy v2.0.0+
"""
from __future__ import unicode_literals, print_function

import os
import plac
import random
import tqdm
from pathlib import Path
import spacy
from spacy.util import minibatch, compounding, decaying, env_opt

# TODO:
# meta?
# meta = util.read_json(meta_path) if meta_path else {}
# if not isinstance(meta, dict):
#     print(error)
# meta.setdefault('lang', lang)
# meta.setdefault('name', 'unnamed')

# from data.cats import sentences as cat_sentences
if os.path.isfile('tests/training/data/cats.py'):
    from data.cats import sentences as cat_sentences
else:
    cat_sentences = None

if os.path.isfile('tests/training/data/horses.py'):
    from data.horses import sentences as horse_sentences
else:
    horse_sentences = None


# new entity label
LABEL = 'ANIMAL'

# training data
# Note: If you're using an existing model, make sure to mix in examples of
# other entity types that spaCy correctly recognized before. Otherwise, your
# model might learn the new type, but "forget" what it previously knew.
# https://explosion.ai/blog/pseudo-rehearsal-catastrophic-forgetting

if not cat_sentences and not horse_sentences:
    print('first generate TRAIN_DATA using: {}/create_biluo.py'.format(os.path.dirname(__file__)))
    exit(-1)

TRAIN_DATA = []
TRAIN_DATA += cat_sentences or []
TRAIN_DATA += horse_sentences or []


# test the trained model
test_texts = [
    'Do you like cats?',
    'A cat pures',
    'cats chase mice',
    'cats who chase their tail',
    'Do you like horses?',
    'People ride horses',
    'A horse is tall',
    'riding horses is fun',
    'The horse is tall',
    'my horse is riding fast',
    'horses run fast',
    '\"Sweet cats,\" Jenn replied.',
    'They didn\'t purr like cats but growled.',
]


def test_model(model_dir, use_gpu):
    print("Loading from", model_dir)
    if (use_gpu >= 0):
        spacy.util.use_gpu(0)
    nlp2 = spacy.load(model_dir)
    for text in test_texts:
        doc2 = nlp2(text)
        for ent in doc2.ents:
            print(ent.label_, ent.text)


def model_exists(model_dir):
    if not model_dir:
        return False
    if not os.path.isdir(model_dir):
        return False
    if not os.listdir(model_dir):
        return False
    return True


def count_train():
    return sum(count_tokens(text) for text, _ in TRAIN_DATA)


def count_tokens(texts):
    if isinstance(texts, tuple) or isinstance(texts, list):
        return sum(count_tokens(txt) for txt in texts)
    if isinstance(texts, str):
        return len(texts.split())

animal_model = os.path.join(os.path.dirname(__file__), 'models/animal')

@plac.annotations(
    model=("Model name. Defaults to blank 'en' model.", "option", "m", str),
    new_model_name=("New model name for model meta.", "option", "nm", str),
    output_dir=("Optional output directory", "option", "o", str),
    use_gpu=("Use GPU", "option", "g", int),
    n_iter=("Number of training iterations", "option", "n", int))
def main(model='en', new_model_name='en-animals', output_dir=animal_model, use_gpu=-1, n_iter=20):
    if model_exists(output_dir):
        print('model exists.')
        test_model(output_dir, use_gpu)
        return

    """Set up the pipeline and entity recognizer, and train the new entity."""
    if model is not None:
        print("Loading model '%s' ... " % model)
        if (use_gpu >= 0):
            spacy.util.use_gpu(0)
        nlp = spacy.load(model)  # load existing spaCy model
    else:
        print("Creating blank 'en' model ... ")
        nlp = spacy.blank('en')  # create blank Language class

    # Add entity recognizer to model if it's not in the pipeline
    # nlp.create_pipe works for built-ins that are registered with spaCy
    if 'ner' not in nlp.pipe_names:
        ner = nlp.create_pipe('ner')
        nlp.add_pipe(ner)
    else:
        # otherwise, get it, so we can add labels to it
        ner = nlp.get_pipe('ner')

    ner.add_label(LABEL)   # add new entity label to entity recognizer

    print('begin training... ')
    if model is None:
        optimizer = nlp.begin_training(device=use_gpu)
    else:
        # Note that 'begin_training' initializes the models, so it'll zero out
        # existing entity types.
        optimizer = nlp.entity.create_optimizer()

    # Take dropout and batch size as generators of values -- dropout
    # starts high and decays sharply, to force the optimizer to explore.
    # Batch size starts at 1 and grows, so that we make updates quickly
    # at the beginning of training.
    dropout_rates = decaying(env_opt('dropout_from', 0.6),
                             env_opt('dropout_to', 0.2),
                             env_opt('dropout_decay', 1e-4))
    batch_sizes = compounding(env_opt('batch_from', 15),
                              env_opt('batch_to', 30),
                              env_opt('batch_compound', 1.005))

    # disable other pipes during training
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != 'ner']
    with nlp.disable_pipes(*other_pipes):  # only train NER
        n_train_words = count_train()
        for i in range(n_iter):
            losses = {}
            random.shuffle(TRAIN_DATA)

            with tqdm.tqdm(total=n_train_words, leave=False) as pbar:
                for batch in minibatch(TRAIN_DATA, size=batch_sizes):
                    texts, annotations = zip(*batch)
                    nlp.update(texts, annotations, sgd=optimizer,
                               drop=next(dropout_rates), losses=losses)
                    pbar.update(count_tokens(texts))
            print('{}/{} loss: {}'.format(i+1, n_iter, losses))

    for text in test_texts:
        doc = nlp(text)
        print("Entities in '%s'" % text)
        for ent in doc.ents:
            print(ent.label_, ent.text)

    # save model to output directory
    if output_dir is not None:
        output_dir = Path(output_dir)
        if not output_dir.exists():
            output_dir.mkdir()
        nlp.meta['name'] = new_model_name  # rename model
        nlp.to_disk(output_dir)
        print("Saved model to", output_dir)

        # test the saved model
        test_model(output_dir, use_gpu)


if __name__ == '__main__':
    plac.call(main)
