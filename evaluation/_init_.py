"""Turns an uploaded PDF into searchable passages.

* ``pdf_loader`` - extracts text page by page, removes repeated headers/footers, reports unreadable files.
* ``chunker``    - splits page text into overlapping, structure-aware passages with page numbers.
"""