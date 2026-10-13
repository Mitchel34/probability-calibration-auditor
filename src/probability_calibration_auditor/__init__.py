"""Dependency-free audits of paired binary probabilities.

The scoring module is loaded only when audit is called. In particular, importing
the receipt exporter cannot import or invoke the evaluation workload.
"""
__version__ = "0.1.0"


def audit(probabilities, outcomes):
    """Return scores and four positive-class reliability bins."""
    from .core import audit as score
    return score(probabilities, outcomes)
