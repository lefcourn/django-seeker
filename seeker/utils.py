from .registry import model_documents
from django.conf import settings
from elasticsearch_dsl.connections import connections
import elasticsearch_dsl as dsl
import sys
import time

def index(obj, index=None, using=None):
    """
    Shortcut to index a Django object based on it's model class.
    """
    from django.contrib.contenttypes.models import ContentType
    model_class = ContentType.objects.get_for_model(obj).model_class()
    for doc_class in model_documents.get(model_class, []):
        doc_using = using or doc_class._doc_type.using or 'default'
        doc_index = index or doc_class._doc_type.index or getattr(settings, 'SEEKER_INDEX', 'seeker')
        es = connections.get_connection(doc_using)
        es.index(
            index=doc_index,
            doc_type=doc_class._doc_type.name,
            body=doc_class.serialize(obj),
            id=doc_class.get_id(obj)
        )

def delete(obj, index=None, using=None):
    """
    Shortcut to delete a Django object from the ES index based on it's model class.
    """
    from django.contrib.contenttypes.models import ContentType
    model_class = ContentType.objects.get_for_model(obj).model_class()
    for doc_class in model_documents.get(model_class, []):
        doc_using = using or doc_class._doc_type.using or 'default'
        doc_index = index or doc_class._doc_type.index or getattr(settings, 'SEEKER_INDEX', 'seeker')
        es = connections.get_connection(doc_using)
        es.delete(
            index=doc_index,
            doc_type=doc_class._doc_type.name,
            id=doc_class.get_id(obj)
        )

def search(models=None, using='default'):
    """
    Returns a search object across the specified models.
    """
    types = []
    indices = []
    if models is None:
        models = model_documents.keys()
    for model_class in models:
        for doc_class in model_documents.get(model_class, []):
            indices.append(doc_class._doc_type.index)
            types.append(doc_class)
    return dsl.Search(using=using).index(*indices).doc_type(*types)

def progress(iterator, count=None, label='', size=40, chars='# ', output=sys.stdout, frequency=1.0):
    """
    An iterator wrapper that writes/updates a progress bar to an output stream (stdout by default).
    Based on http://code.activestate.com/recipes/576986-progress-bar-for-console-programs-as-iterator/
    """
    assert len(chars) >= 2
    if label:
        label = unicode(label) + ' '

    try:
        count = len(iterator)
    except:
        pass

    start = time.time()

    def show(i):
        if count:
            x = int(size * i / count)
            bar = '[%s%s]' % (chars[0] * x, chars[1] * (size - x))
            pct = int((100.0 * i) / count)
            status = '%s/%s %s%%' % (i, count, pct)
        else:
            bar = ''
            status = str(i)
        e = time.time() - start
        mins, s = divmod(int(e), 60)
        h, m = divmod(mins, 60)
        elapsed = '%d:%02d:%02d' % (h, m, s) if h else '%02d:%02d' % (m, s)
        speed = '%.2f iters/sec' % (i / e) if e > 0 else ''
        output.write('%s%s %s - %s, %s\r' % (label, bar, status, elapsed, speed))
        output.flush()

    show(0)
    last_update = 0.0
    processed = 0
    for item in iterator:
        yield item
        processed += 1
        since = time.time() - last_update
        if since >= frequency:
            show(processed)
            last_update = time.time()
    show(processed)

    output.write('\n')
    output.flush()
