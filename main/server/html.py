"""
Html utility functions.
"""
import re, string, mimetypes, os, json, random, hashlib,  unittest
from django.template import RequestContext, loader
from django.core.servers.basehttp import FileWrapper
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.core.context_processors import csrf
from django.core.paginator import Paginator, InvalidPage, EmptyPage

from BeautifulSoup import BeautifulSoup, Comment

import markdown2
from docutils import core
import docutils.parsers.rst.roles
docutils.parsers.rst.roles.DEFAULT_INTERPRETED_ROLE = 'title-reference'
from itertools import groupby

# safe string transformation
import string
SAFE_TAG = set(string.ascii_letters + string.digits + "._-")

def safe_tag(text):
    global SAFE_TAG
    def change(x):
        return x if x in SAFE_TAG else "."
    text = ''.join(map(change, text))
    return text.lower()
    
def get_page(request, obj_list, per_page=25):
    "A generic paginator"

    paginator = Paginator(obj_list, per_page) 
    try:
        pid = int(request.GET.get('page', '1'))
    except ValueError:
        pid = 1

    try:
        page = paginator.page(pid)
    except (EmptyPage, InvalidPage):
        page = paginator.page(paginator.num_pages)
    
    return page

def nuke(text):
    """
    This function is not the main sanitizer,
    is used mainly as an extra precaution to preemtively
    delete markup from markdown content.
    """
    text = text.replace("<","&lt;")
    text = text.replace(">","&gt;")
    text = text.replace("\"","&quot;")
    text = text.replace("&","&amp;")
    return text

def generate(text):
    if not text:
        return ""
    if text.startswith('##rest'):
        # this is a django bugfix!
        docutils.parsers.rst.roles.DEFAULT_INTERPRETED_ROLE = 'title-reference'
        text = text[6:].strip()
        rest = core.publish_parts(text ,writer_name='html')
        html = rest.get('html_body','[rest error]')
    else:
        md = markdown2.Markdown( safe_mode=True )
        md.html_removed_text="[HTML]"
        text = fix_orphans(text)
        html = md.convert(text)
        html = extra_html(html)
    return html

orphans = re.compile("(^|[\w:.]\s)((https?|ftp):\S+) ", re.MULTILINE | re.VERBOSE)
def fix_orphans(text):
    global orphans
    "Add markdown to orphan links"
    text = orphans.sub(r'\1<\2>', text)
    return text

youtube = re.compile("youtube:([\w-]+) ", re.MULTILINE | re.VERBOSE)
def extra_html(text):
    "Allows embedding extra html features"
    frame = r'''
    <div>
        <iframe width="560" height="315" src="http://www.youtube.com/embed/\1" frameborder="0" allowfullscreen></iframe>
    </div>
    <div>Click to go to <a href="http://www.youtube.com/watch?v=\1">YouTube</a></div>
    '''
    text = youtube.sub(frame, text)
    return text

ALLOWED_TAGS = "strong span:class br ol ul li a:href img:src pre code blockquote p em"
def sanitize(value, allowed_tags=ALLOWED_TAGS):
    """
    From http://djangosnippets.org/snippets/1655/

    Argument should be in form 'tag2:attr1:attr2 tag2:attr1 tag3', where tags
    are allowed HTML tags, and attrs are the allowed attributes for that tag.
    """
    js_regex = re.compile(r'[\s]*(&#x.{1,7})?'.join(list('javascript')))
    allowed_tags = [tag.split(':') for tag in allowed_tags.split()]
    allowed_tags = dict((tag[0], tag[1:]) for tag in allowed_tags)

    soup = BeautifulSoup(value)
    for comment in soup.findAll(text=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.findAll(True):
        if tag.name not in allowed_tags:
            tag.hidden = True
        else:
            tag.attrs = [(attr, js_regex.sub('', val)) for attr, val in tag.attrs
                         if attr in allowed_tags[tag.name]]

    return soup.renderContents().decode('utf8')

class Params(object):
    """
    Represents incoming parameters. 
    Parameters with special meaning: q - search query, m - matching
    Keyword arguments
    will be defaults.

    >>> p = Params(a=1, b=2, c=3, incoming=dict(c=4))
    >>> p.a, p.b, p.c
    (1, 2, 4)
    """
    def __init__(self, **kwds):
        self.q = ''
        self.__dict__.update(kwds)
        
    def parse(self, request):
        self.q = request.GET.get('q', '')
        if self.q:
            self.setr('Searching for %s' % self.q)
    
    def get(self, key, default=''):
        return self.__dict__.get(key, default)
        
    def update(self, data):
        self.__dict__.update(data)

    def __getitem__(self, key):
        return self.__dict__[key]

    def __repr__(self):
        return 'Params: %s' % self.__dict__
    
    def setr(self, text):
        setattr(self, 'remind', text)

    def getr(self,text):
        return getattr(self, 'remind')

def response(data, **kwd):
    """Returns a http response"""
    return HttpResponse(data, **kwd)
    
def json_response(adict, **kwd):
    """Returns a http response in JSON format from a dictionary"""
    return HttpResponse(json.dumps(adict), **kwd)

def redirect(url):
    "Redirects to a url"
    return HttpResponseRedirect(url)

def template(request, name, mimetype=None, **kwd):
    """Renders a template and returns it as an http response"""
    
    # parameters that will always be available for the template
    kwd['request'] = request
    return render_to_response(name, kwd, context_instance=RequestContext(request))

# stripping html tags from: http://stackoverflow.com/questions/753052/strip-html-from-strings-in-python
from HTMLParser import HTMLParser

class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(text):
    try:
        s = MLStripper()
        s.feed(text)
        return s.get_data()    
    except Exception, exc:
        return "unable to strip tags %s" % exc
    
class HtmlTest(unittest.TestCase):
    def test_sanitize(self):
        "Testing HTML sanitization"
        text = sanitize('<a href="javascrip:something">A</a>', allowed_tags="b")
        self.assertEqual( text, u'A' )

        p = Params(a=1, b=2, c=3)
        self.assertEqual( (p.a, p.b, p.c), (1, 2, 3))

def suite():
    s = unittest.TestLoader().loadTestsFromTestCase(HtmlTest)
    return s
