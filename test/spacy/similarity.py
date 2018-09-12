#!nlp/bin/python

import spacy

nlp = spacy.load('en_core_web_md')  # make sure to use larger model!
tokens = nlp(u'dog cat banana')
#tokens = nlp(u'king queen sultan ceasar')

for token1 in tokens:
    for token2 in tokens:
        print(token1.text, token2.text, token1.similarity(token2))
