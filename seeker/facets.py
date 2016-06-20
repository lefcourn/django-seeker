from django.conf import settings
from elasticsearch_dsl import A, Q
import functools
import operator
import copy

class Facet (object):
    field = None
    label = None
    template = getattr(settings, 'SEEKER_DEFAULT_FACET_TEMPLATE', 'seeker/facets/terms.html')

    def __init__(self, field, label=None, name=None, description=None, template=None, **kwargs):
        self.field = field
        self.label = label or self.field.replace('_', ' ').replace('.raw', '').replace('.', ' ').capitalize()
        self.name = (name or self.field).replace('.raw', '').replace('.', '_')
        self.template = template or self.template
        self.description = description
        self.kwargs = kwargs

    def apply(self, search, **extra):
        return search

    def filter(self, search, values):
        return search

    def data(self, response, values=[]):
        try:
            return response.aggregations[self.name].to_dict()
        except:
            return {}

    def get_key(self, bucket):
        return bucket.get('key')

    def buckets(self, response):
        for b in self.data(response).get('buckets', []):
            yield self.get_key(b), b.get('doc_count')

class TermsFacet (Facet):

    def __init__(self, field, **kwargs):
        self.filter_operator = kwargs.pop('filter_operator', 'or')
        super(TermsFacet, self).__init__(field, **kwargs)

    def apply(self, search, **extra):
        params = {'field': self.field}
        params.update(self.kwargs)
        params.update(extra)
        search.aggs[self.name] = A('terms', **params)
        return search

    def filter(self, search, values):
        if len(values) > 1:
            if self.filter_operator.lower() == 'and':
                filters = [Q('term', **{self.field: v}) for v in values]
                return search.query(functools.reduce(operator.and_, filters))
            else:
                return search.filter('terms', **{self.field: values})
        elif len(values) == 1:
            return search.filter('term', **{self.field: values[0]})
        return search

class GlobalTermsFacet (TermsFacet):

    def apply(self, search):
        top = A('global')
        top[self.field] = self.aggregation
        search.aggs[self.field] = top
        return search

    def data(self, response, values=[]):
        return response.aggregations[self.field][self.field].to_dict()

class YearHistogram (Facet):
    template = 'seeker/facets/year_histogram.html'

    def apply(self, search, **extra):
        params = {
            'field': self.field,
            'interval': 'year',
            'format': 'yyyy',
            'min_doc_count': 1,
            'order': {'_key': 'desc'},
        }
        params.update(self.kwargs)
        params.update(extra)
        search.aggs[self.name] = A('date_histogram', **params)
        return search

    def filter(self, search, values):
        filters = []
        for val in values:
            kw = {
                self.field: {
                    'gte': '%s-01-01T00:00:00' % val,
                    'lte': '%s-12-31T23:59:59' % val,
                }
            }
            filters.append(Q('range', **kw))
        return search.query(functools.reduce(operator.or_, filters))

    def get_key(self, bucket):
        return bucket.get('key_as_string')

class RangeFilter (Facet):
    """
    Facet used for ranges of digits
    Optional:
        ranges - list of dictionaries containing two keys: one 'gt' (or 'gte') and one 'lt' (or 'lte').
                 When provided, this facet will ONLY filter on those ranges. Any other ranges are ignored.
    """
    template = 'seeker/facets/range.html'
    
    def __init__(self, field, **kwargs):
        self.ranges = kwargs.pop('ranges', [])
        super(RangeFilter, self).__init__(field, **kwargs)
        
    def apply(self, search, **extra):
        if self.ranges:
            params = {'field': self.field, 'ranges': self.ranges}
            params.update(extra)
            search.aggs[self.name] = A('range', **params)
        return search

    def filter(self, search, values):
        if self.ranges:
            valid_ranges = []
            # We only accept ranges that are defined
            for range in self.ranges:
                range_value = str(range.get('key'))
                if range_value in values:
                    valid_ranges.append(range)
            filters = []
            for range in valid_ranges:
                translated_range = {}
                if 'from' in range:
                    translated_range['gte'] = range['from']
                if 'to' in range:
                    translated_range['lt'] = range['to']
                if translated_range:
                    filters.append(F('range', **{self.field: translated_range}))
            if filters:
                search = search.filter(functools.reduce(operator.or_, filters))
        else:
            if len(values) == 2:
                r = {}
                if values[0].isdigit():
                    r['gte'] = values[0]
                if values[1].isdigit():
                    r['lte'] = values[1]
                search = search.filter('range', **{self.field: r})
        return search
    
    def data(self, response, values=[]):
        try:
            facet_data = response.aggregations[self.name].to_dict()
            buckets = copy.deepcopy(facet_data['buckets'])
            for bucket in buckets:
                if bucket['key'] not in values and bucket['doc_count'] == 0:
                    facet_data['buckets'].remove(bucket)
            return facet_data
        except:
            return {}
    
    def in_range(self, range_key, value):
        for range in self.ranges:
            if range['key'] == range_key:
                if 'from' in range and range['from'] > value:
                    return False
                if 'to' in range and range['to'] <= value:
                    return False
                return True
        return False