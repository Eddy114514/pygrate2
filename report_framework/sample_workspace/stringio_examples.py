from StringIO import StringIO
text_buf = StringIO()

import StringIO
text_buf2 = StringIO.StringIO()

from cStringIO import StringIO
bytes_buf = StringIO("abc")

import cStringIO
bytes_buf2 = cStringIO.StringIO("abc")

import StringIO as sio
warning_only_alias = sio.StringIO()
