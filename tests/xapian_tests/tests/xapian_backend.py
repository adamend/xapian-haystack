# Copyright (C) 2009 David Sauve, Trapeze.  All rights reserved.

import cPickle as pickle
import datetime
import os
import shutil
import xapian

from django.conf import settings
from django.db import models
from django.test import TestCase

from haystack import indexes, sites
from haystack.backends.xapian_backend import SearchBackend, _marshal_value

from core.models import MockTag, AnotherMockModel


class XapianMockModel(models.Model):
    """
    Same as tests.core.MockModel with a few extra fields for testing various
    sorting and ordering criteria.
    """
    author = models.CharField(max_length=255)
    foo = models.CharField(max_length=255, blank=True)
    pub_date = models.DateTimeField(default=datetime.datetime.now)
    tag = models.ForeignKey(MockTag)

    value = models.IntegerField(default=0)
    flag = models.BooleanField(default=True)
    slug = models.SlugField()
    popularity = models.FloatField(default=0.0)

    def __unicode__(self):
        return self.author
    
    def hello(self):
        return 'World!'


class XapianMockSearchIndex(indexes.SearchIndex):
    text = indexes.CharField(
        document=True, use_template=True, 
        template_name='search/indexes/core/mockmodel_text.txt'
    )
    name = indexes.CharField(model_attr='author')
    pub_date = indexes.DateField(model_attr='pub_date')
    value = indexes.IntegerField(model_attr='value')
    flag = indexes.BooleanField(model_attr='flag')
    slug = indexes.CharField(indexed=False, model_attr='slug')
    popularity = indexes.FloatField(model_attr='popularity')
    sites = indexes.MultiValueField()

    def prepare_sites(self, obj):
        return ['%d' % (i * obj.id) for i in xrange(1, 4)]


class XapianSearchSite(sites.SearchSite):
    pass


class XapianSearchBackendTestCase(TestCase):
    def setUp(self):
        super(XapianSearchBackendTestCase, self).setUp()
        
        self.site = XapianSearchSite()
        self.sb = SearchBackend(site=self.site)
        self.msi = XapianMockSearchIndex(XapianMockModel, backend=self.sb)
        self.site.register(XapianMockModel, XapianMockSearchIndex)
        
        self.sample_objs = []
        
        for i in xrange(1, 4):
            mock = XapianMockModel()
            mock.id = i
            mock.author = 'david%s' % i
            mock.pub_date = datetime.date(2009, 2, 25) - datetime.timedelta(days=i)
            mock.value = i * 5
            mock.flag = bool(i % 2)
            mock.slug = 'http://example.com/%d' % i
            self.sample_objs.append(mock)
            
        self.sample_objs[0].popularity = 834.0
        self.sample_objs[1].popularity = 35.5
        self.sample_objs[2].popularity = 972.0
    
    def tearDown(self):
        if os.path.exists(settings.HAYSTACK_XAPIAN_PATH):
            shutil.rmtree(settings.HAYSTACK_XAPIAN_PATH)

        super(XapianSearchBackendTestCase, self).tearDown()
    
    def xapian_search(self, query_string):
        database = xapian.Database(settings.HAYSTACK_XAPIAN_PATH)
        if query_string:
            qp = xapian.QueryParser()
            qp.set_database(database)
            query = qp.parse_query(query_string, xapian.QueryParser.FLAG_WILDCARD)
        else:
            query = xapian.Query(query_string) # Empty query matches all
        enquire = xapian.Enquire(database)
        enquire.set_query(query)
        matches = enquire.get_mset(0, database.get_doccount())
        
        document_list = []
        
        for match in matches:
            document = match.get_document()
            app_label, module_name, pk, model_data = pickle.loads(document.get_data())
            for key, value in model_data.iteritems():
                model_data[key] = _marshal_value(value)
            model_data['id'] = u'%s.%s.%d' % (app_label, module_name, pk)
            document_list.append(model_data)

        return document_list
    
    def silly_test(self):
        
        self.sb.update(self.msi, self.sample_objs)
        
        self.assertEqual(len(self.xapian_search('indexed')), 3)
        self.assertEqual(len(self.xapian_search('Indexed')), 3)
    
    def test_update(self):
        self.sb.update(self.msi, self.sample_objs)
        
        self.assertEqual(len(self.xapian_search('')), 3)
        self.assertEqual([dict(doc) for doc in self.xapian_search('')], [
            {'flag': u't', 'name': u'david1', 'text': u'indexed!\n1', 'sites': u"['1', '2', '3']", 'pub_date': u'20090224000000', 'value': u'000000000005', 'id': u'tests.xapianmockmodel.1', 'slug': u'http://example.com/1', 'popularity': '\xca\x84', 'django_id': u'1', 'django_ct': u'tests.xapianmockmodel'},
            {'flag': u'f', 'name': u'david2', 'text': u'indexed!\n2', 'sites': u"['2', '4', '6']", 'pub_date': u'20090223000000', 'value': u'000000000010', 'id': u'tests.xapianmockmodel.2', 'slug': u'http://example.com/2', 'popularity': '\xb4p', 'django_id': u'2', 'django_ct': u'tests.xapianmockmodel'},
            {'flag': u't', 'name': u'david3', 'text': u'indexed!\n3', 'sites': u"['3', '6', '9']", 'pub_date': u'20090222000000', 'value': u'000000000015', 'id': u'tests.xapianmockmodel.3', 'slug': u'http://example.com/3', 'popularity': '\xcb\x98', 'django_id': u'3', 'django_ct': u'tests.xapianmockmodel'}
        ])
        import pdb; pdb.set_trace()

    def test_duplicate_update(self):
        self.sb.update(self.msi, self.sample_objs)
        self.sb.update(self.msi, self.sample_objs) # Duplicates should be updated, not appended -- http://github.com/notanumber/xapian-haystack/issues/#issue/6
        
        self.assertEqual(len(self.xapian_search('')), 3)

    def test_remove(self):
        self.sb.update(self.msi, self.sample_objs)
        self.assertEqual(len(self.xapian_search('')), 3)
        
        self.sb.remove(self.sample_objs[0])
        self.assertEqual(len(self.xapian_search('')), 2)
        self.assertEqual([dict(doc) for doc in self.xapian_search('')], [
            {'flag': u'f', 'name': u'david2', 'text': u'indexed!\n2', 'sites': u"['2', '4', '6']", 'pub_date': u'20090223000000', 'value': u'000000000010', 'id': u'tests.xapianmockmodel.2', 'slug': u'http://example.com/2', 'popularity': '\xb4p', 'django_id': u'2', 'django_ct': u'tests.xapianmockmodel'},
            {'flag': u't', 'name': u'david3', 'text': u'indexed!\n3', 'sites': u"['3', '6', '9']", 'pub_date': u'20090222000000', 'value': u'000000000015', 'id': u'tests.xapianmockmodel.3', 'slug': u'http://example.com/3', 'popularity': '\xcb\x98', 'django_id': u'3', 'django_ct': u'tests.xapianmockmodel'}
        ])
    
    def test_clear(self):
        self.sb.update(self.msi, self.sample_objs)
        self.assertEqual(len(self.xapian_search('')), 3)
        
        self.sb.clear()
        self.assertEqual(len(self.xapian_search('')), 0)
        
        self.sb.update(self.msi, self.sample_objs)
        self.assertEqual(len(self.xapian_search('')), 3)
        
        self.sb.clear([AnotherMockModel])
        self.assertEqual(len(self.xapian_search('')), 3)
        
        self.sb.clear([XapianMockModel])
        self.assertEqual(len(self.xapian_search('')), 0)
        
        self.sb.update(self.msi, self.sample_objs)
        self.assertEqual(len(self.xapian_search('')), 3)
        
        self.sb.clear([AnotherMockModel, XapianMockModel])
        self.assertEqual(len(self.xapian_search('')), 0)
    
    def test_search(self):
        self.sb.update(self.msi, self.sample_objs)
        self.assertEqual(len(self.xapian_search('')), 3)
        
        # Empty query
        self.assertEqual(self.sb.search(xapian.Query()), {'hits': 0, 'results': []})
        
        # Wildcard -- All
        self.assertEqual(self.sb.search(xapian.Query(''))['hits'], 3)
        self.assertEqual([result.pk for result in self.sb.search(xapian.Query(''))['results']], [1, 2, 3])
        
    # def test_field_facets(self):
    #     self.sb.update(self.msi, self.sample_objs)
    #     self.assertEqual(len(self.xapian_search('')), 3)
    #     
    #     self.assertEqual(self.sb.search('', facets=['name']), {'hits': 0, 'results': []})
    #     results = self.sb.search('index', facets=['name'])
    #     self.assertEqual(results['hits'], 3)
    #     self.assertEqual(results['facets']['fields']['name'], [('david1', 1), ('david2', 1), ('david3', 1)])
    # 
    #     results = self.sb.search('index', facets=['flag'])
    #     self.assertEqual(results['hits'], 3)
    #     self.assertEqual(results['facets']['fields']['flag'], [(False, 1), (True, 2)])
    #     
    #     results = self.sb.search('index', facets=['sites'])
    #     self.assertEqual(results['hits'], 3)
    #     self.assertEqual(results['facets']['fields']['sites'], [('1', 1), ('3', 2), ('2', 2), ('4', 1), ('6', 2), ('9', 1)])
            
    # def test_date_facets(self):
    #     self.sb.update(self.msi, self.sample_objs)
    #     self.assertEqual(len(self.xapian_search('')), 3)
    # 
    #     self.assertEqual(self.sb.search('', date_facets={'pub_date': {'start_date': datetime.datetime(2008, 10, 26), 'end_date': datetime.datetime(2009, 3, 26), 'gap_by': 'month'}}), {'hits': 0, 'results': []})
    #     results = self.sb.search('index', date_facets={'pub_date': {'start_date': datetime.datetime(2008, 10, 26), 'end_date': datetime.datetime(2009, 3, 26), 'gap_by': 'month'}})
    #     self.assertEqual(results['hits'], 3)
    #     self.assertEqual(results['facets']['dates']['pub_date'], [
    #         ('2009-02-26T00:00:00', 0),
    #         ('2009-01-26T00:00:00', 3),
    #         ('2008-12-26T00:00:00', 0),
    #         ('2008-11-26T00:00:00', 0),
    #         ('2008-10-26T00:00:00', 0),
    #     ])
    # 
    #     results = self.sb.search('index', date_facets={'pub_date': {'start_date': datetime.datetime(2009, 02, 01), 'end_date': datetime.datetime(2009, 3, 15), 'gap_by': 'day', 'gap_amount': 15}})
    #     self.assertEqual(results['hits'], 3)
    #     self.assertEqual(results['facets']['dates']['pub_date'], [
    #         ('2009-03-03T00:00:00', 0),
    #         ('2009-02-16T00:00:00', 3),
    #         ('2009-02-01T00:00:00', 0)
    #     ])

    # def test_query_facets(self):
    #     self.sb.update(self.msi, self.sample_objs)
    #     self.assertEqual(len(self.xapian_search('')), 3)
    # 
    #     self.assertEqual(self.sb.search('', query_facets={'name': 'da*'}), {'hits': 0, 'results': []})
    #     results = self.sb.search('index', query_facets={'name': 'da*'})
    #     self.assertEqual(results['hits'], 3)
    #     self.assertEqual(results['facets']['queries']['name'], ('da*', 3))
    
    # def test_narrow_queries(self):
    #     self.sb.update(self.msi, self.sample_objs)
    #     self.assertEqual(len(self.xapian_search('')), 3)
    #     
    #     self.assertEqual(self.sb.search('', narrow_queries=set(['name:david1'])), {'hits': 0, 'results': []})
    #     results = self.sb.search('index', narrow_queries=set(['name:david1']))
    #     self.assertEqual(results['hits'], 1)
    
    # def test_highlight(self):
    #     self.sb.update(self.msi, self.sample_objs)
    #     self.assertEqual(len(self.xapian_search('')), 3)
    #     
    #     self.assertEqual(self.sb.search('', highlight=True), {'hits': 0, 'results': []})
    #     self.assertEqual(self.sb.search('Index', highlight=True)['hits'], 3)
    #     self.assertEqual([result.highlighted['text'] for result in self.sb.search('Index', highlight=True)['results']], ['<em>Index</em>ed!\n1', '<em>Index</em>ed!\n2', '<em>Index</em>ed!\n3'])
    
    # def test_spelling_suggestion(self):
    #     self.sb.update(self.msi, self.sample_objs)
    #     self.assertEqual(len(self.xapian_search('')), 3)
    #     
    #     self.assertEqual(self.sb.search('indxe')['hits'], 0)
    #     self.assertEqual(self.sb.search('indxe')['spelling_suggestion'], 'indexed')
    #     
    #     self.assertEqual(self.sb.search('indxed')['hits'], 0)
    #     self.assertEqual(self.sb.search('indxed')['spelling_suggestion'], 'indexed')
    #     
    #     self.assertEqual(self.sb.search('indx')['hits'], 0)
    #     self.assertEqual(self.sb.search('indx', spelling_query='indexy')['spelling_suggestion'], 'indexed')

    # def test_more_like_this(self):
    #     self.sb.update(self.msi, self.sample_objs)
    #     self.assertEqual(len(self.xapian_search('')), 3)
    #     
    #     results = self.sb.more_like_this(self.sample_objs[0])
    #     self.assertEqual(results['hits'], 2)
    #     self.assertEqual([result.pk for result in results['results']], [3, 2])
    # 
    #     results = self.sb.more_like_this(self.sample_objs[0], additional_query_string='david3')
    #     self.assertEqual(results['hits'], 1)
    #     self.assertEqual([result.pk for result in results['results']], [3])

    # def test_order_by(self):
    #     self.sb.update(self.msi, self.sample_objs)
    #     
    #     results = self.sb.search('*', sort_by=['pub_date'])
    #     self.assertEqual([result.pk for result in results['results']], [3, 2, 1])
    #     
    #     results = self.sb.search('*', sort_by=['-pub_date'])
    #     self.assertEqual([result.pk for result in results['results']], [1, 2, 3])
    # 
    #     results = self.sb.search('*', sort_by=['id'])
    #     self.assertEqual([result.pk for result in results['results']], [1, 2, 3])
    # 
    #     results = self.sb.search('*', sort_by=['-id'])
    #     self.assertEqual([result.pk for result in results['results']], [3, 2, 1])
    # 
    #     results = self.sb.search('*', sort_by=['value'])
    #     self.assertEqual([result.pk for result in results['results']], [1, 2, 3])
    # 
    #     results = self.sb.search('*', sort_by=['-value'])
    #     self.assertEqual([result.pk for result in results['results']], [3, 2, 1])
    # 
    #     results = self.sb.search('*', sort_by=['popularity'])
    #     self.assertEqual([result.pk for result in results['results']], [2, 1, 3])
    # 
    #     results = self.sb.search('*', sort_by=['-popularity'])
    #     self.assertEqual([result.pk for result in results['results']], [3, 1, 2])
    # 
    #     results = self.sb.search('*', sort_by=['flag', 'id'])
    #     self.assertEqual([result.pk for result in results['results']], [2, 1, 3])
    # 
    #     results = self.sb.search('*', sort_by=['flag', '-id'])
    #     self.assertEqual([result.pk for result in results['results']], [2, 3, 1])

    # def test_boost(self):
    #     self.sb.update(self.msi, self.sample_objs)
    # 
    #      # TODO: Need a better test case here.  Possibly better test data?
    #     results = self.sb.search('*', boost={'true': 2})
    #     self.assertEqual([result.pk for result in results['results']], [1, 3, 2])
    # 
    #     results = self.sb.search('*', boost={'true': 1.5})
    #     self.assertEqual([result.pk for result in results['results']], [1, 3, 2])

    def test__marshal_value(self):
        self.assertEqual(_marshal_value('abc'), u'abc')
        self.assertEqual(_marshal_value(1), '000000000001')
        self.assertEqual(_marshal_value(2653), '000000002653')
        self.assertEqual(_marshal_value(25.5), '\xb2`')
        self.assertEqual(_marshal_value([1, 2, 3]), u'[1, 2, 3]')
        self.assertEqual(_marshal_value((1, 2, 3)), u'(1, 2, 3)')
        self.assertEqual(_marshal_value({'a': 1, 'c': 3, 'b': 2}), u"{'a': 1, 'c': 3, 'b': 2}")
        self.assertEqual(_marshal_value(datetime.datetime(2009, 5, 9, 16, 14)), u'20090509161400')
        self.assertEqual(_marshal_value(datetime.datetime(2009, 5, 9, 0, 0)), u'20090509000000')
        self.assertEqual(_marshal_value(datetime.datetime(1899, 5, 18, 0, 0)), u'18990518000000')
        self.assertEqual(_marshal_value(datetime.datetime(2009, 5, 18, 1, 16, 30, 250)), u'20090518011630000250')

    def test_build_schema(self):
        (content_field_name, fields) = self.sb.build_schema(self.site.all_searchfields())
        self.assertEqual(content_field_name, 'text')
        self.assertEqual(len(fields), 7)
        self.assertEqual(fields, [
            {'column': 0, 'field_name': 'name', 'type': 'text', 'multi_valued': 'false'},
            {'column': 1, 'field_name': 'text', 'type': 'text', 'multi_valued': 'false'},
            {'column': 2, 'field_name': 'popularity', 'type': 'float', 'multi_valued': 'false'},
            {'column': 3, 'field_name': 'sites', 'type': 'text', 'multi_valued': 'true'},
            {'column': 4, 'field_name': 'value', 'type': 'long', 'multi_valued': 'false'},
            {'column': 5, 'field_name': 'flag', 'type': 'boolean', 'multi_valued': 'false'},
            {'column': 6, 'field_name': 'pub_date', 'type': 'date', 'multi_valued': 'false'},
        ])
