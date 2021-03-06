import spacy
from spacy.tokens import Doc
from collections import Counter
from gensim.summarization import keywords

SIMILARITY_TRESHOLD = 0.90


class Wordmap(object):
    def __init__(self, text, nlp, method='noun_chunks'):
        # lilo
        if (method == 'noun_chunks'):
            self.create_wordmap_from_noun_chunks(text, nlp)
        elif (method == 'entities'):
            self.create_wordmap_from_entities(text, nlp)
        elif (method == 'tokens'):
            self.create_wordmap_from_tokens(text, nlp)
        elif (method == 'gensim'):
            self.create_wordmap_from_gensim_keywords(text, nlp)
        else:  # default
            self.create_wordmap_from_noun_chunks(text, nlp)

    def create_wordmap_from_gensim_keywords(self, text, nlp):
        self.words = Counter(keywords(text).split('\n'))
        return self.words

    def create_wordmap_from_noun_chunks(self, text, nlp):
        self.words = {}
        with nlp.disable_pipes('nlpy_relations'):
            doc = nlp(text)
            self.words = Counter(
                chunk.lemma_ for chunk in doc.noun_chunks if self.filter_noun_chunk(chunk))
        return self.words

    def filter_noun_chunk(self, chunk):  # inner chunk filter
        if len(chunk) == 1:  # a single token
            if (chunk[0].pos_ in ('ADV', 'PRON', 'SPACE')):
                return False
            # lilo (filter some entity types): if (chunk[0].ent_type_)
        return True

    def create_wordmap_from_tokens(self, text, nlp):
        self.words = {}
        with nlp.disable_pipes('nlpy_relations'):
            doc = nlp(text)
            self.words = Counter(t.lemma_ for t in doc if self.filter_token(t))
        return self.words

    def filter_token(self, t):  # inner token filter
        if t.is_stop:
            return False
        if t.is_punct:
            return False
        if t.pos_ in ('ADV', 'PRON', 'SPACE'):
            return False
        return True

    def create_wordmap_from_entities(self, text, nlp):
        self.words = {}
        with nlp.disable_pipes('nlpy_relations'):
            doc = nlp(text)

            # start with each entity in its own cluster
            clusters = [Cluster(e) for e in doc.ents if self.filter_entity(e)]

            # cluster same entities together
            clusters = self.cluster(clusters)

            # generate wordmap
            self.words = Counter(
                c.leader.text for c in clusters for item in c.items)

        return self.words

    def filter_entity(self, e):
        if (e.label_ in ('DATE', 'TIME', 'NORP', 'NUM', 'CARDINAL')):
            return False
        return True

    def cluster(self, clusters):
        if not clusters or len(clusters) < 2:
            return clusters

        any_merge_occured = False
        new_clusters = []
        for c1 in clusters:
            if c1.merged:
                continue
            for c2 in clusters:
                if c2.merged:
                    continue
                if (c1 == c2):
                    continue
                if self.should_merge(c1, c2):
                    new_clusters.append(Cluster.merge(c1, c2))
                    any_merge_occured = True
                    break
            if not c1.merged:
                new_clusters.append(c1)
        if any_merge_occured:
            return self.cluster(new_clusters)  # recurse here
        return clusters

    def should_merge(self, c1, c2):
        if (c1.leader.label != c2.leader.label):
            return False

        # check leader entities similarity
        span1 = c1.leader
        span2 = c2.leader

        # compare entities using similarity function
        sim = span1.similarity(span2)
        if (sim >= SIMILARITY_TRESHOLD):
            return True

        # merge names, e.g: 'Thrun' and 'Sebastian Thrun'
        # but not 'Hillary Clinton' and 'Bill Clinton'
        if (c1.leader.label_ in ('PERSON', 'ORG')):
            set1 = set([t.lower_ for t in span1])
            set2 = set([t.lower_ for t in span2])
            set3 = set1.intersection(set2)
            if (len(set3) / (len(set1) + len(set2)) > 0.3):
                return True

        return False


class Cluster(object):
    def __init__(self, item=None):
        if item:
            self.leader = item
            self.items = set([item])
        else:
            self.leader = None
            self.items = set([])
        self.merged = False

    def add(self, item):
        self.items.add(item)
        if (not self.leader):
            self.leader = item

    @staticmethod
    def merge(c1, c2):
        if not isinstance(c1, Cluster) or not isinstance(c2, Cluster):
            raise Exception()
        c = Cluster()
        c.items = c1.items.union(c2.items)
        c.leader = Cluster.select_leader(c1, c2)
        c1.merged = True
        c2.merged = True
        return c

    @staticmethod
    def select_leader(c1, c2):
        if not c1.leader:
            return c2.leader
        if not c2.leader:
            return c1.leader

        # TODO - how should we decide which leader to use?
        if (len(c1.leader) >= len(c2.leader)):
            return c1.leader

        return c2.leader
