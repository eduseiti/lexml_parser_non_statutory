"""Synthetic fixtures for constructs the 15-sample corpus cannot reach.

The corpus stands in for 300+ unseen documents, so the shapes it happens *not*
to contain are exactly the ones most likely to arrive uncovered. Amendment
A-1.3 (decomposed Unicode) and A-4.6 (a contiguous multi-level Word list)
established the response: build the missing construct by hand and test against
it, rather than leave the branch unexercised or, worse, tune a rule to the
fifteen documents that exist.

Everything here is built **in process** and written into ``tmp_path``. Nothing
binary is committed, so a reviewer reads how a case is constructed rather than
taking a checked-in blob on trust, and a fixture cannot silently rot against a
reader change it was meant to exercise.
"""

from __future__ import annotations
