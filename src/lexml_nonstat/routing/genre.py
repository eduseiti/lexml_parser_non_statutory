"""Genre priors — §2.7: "priors, not rules".

The corpus makes the point on its own. `port_mf_277` is an articulated Portaria
and `port_mf_454` is a Portaria with `1.`, `2.1` and `a)` and no article at all.
Same genre, opposite structure. So a genre may *lean* a document towards the
statutory route and may never decide it, and the numbers below are deliberately
small enough that no prior can clear the gates by itself.

The priors are keyed on the Cycle 2 profile name, because that is the only
genre signal the pipeline actually has — and it is derived from the epigraph,
which is where the document states its own genre.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DEFAULT_PRIOR", "GenrePrior", "PRIORS", "genre_prior"]


@dataclass(frozen=True)
class GenrePrior:
    """A genre's prior probability of being articulated, and why."""

    profile: str
    p_norma: float
    note: str

    def to_dict(self) -> dict[str, object]:
        return {"profile": self.profile, "p_norma": self.p_norma, "note": self.note}


#: Profile name -> prior. Every value sits below the 0.5 mark except
#: `portaria`, and even that is only 0.45: the evidence has to carry the route.
PRIORS: dict[str, GenrePrior] = {
    "portaria": GenrePrior(
        "portaria",
        0.45,
        "Portarias and Resoluções are often articulated — but port_mf_454 is a "
        "Portaria numbered 1., 2.1, a), so this leans and never decides (§2.7)",
    ),
    "parecer": GenrePrior(
        "parecer",
        0.15,
        "Pareceres argue and quote; the three in the corpus quote statutes they "
        "do not enact (§2.5)",
    ),
    "ato_declaratorio": GenrePrior(
        "ato_declaratorio",
        0.20,
        "Atos declaratórios DECLARE and enumerate incisos; none in the corpus "
        "carries an article",
    ),
    "jurisprudencia_generico": GenrePrior(
        "jurisprudencia_generico",
        0.10,
        "Súmulas and acórdãos are never articulated (decision #2)",
    ),
    "servico": GenrePrior(
        "servico",
        0.15,
        "Service documentation is prose under Word heading styles",
    ),
    "generic": GenrePrior(
        "generic",
        0.30,
        "No genre recognised: the neutral prior, since the 285 unseen documents "
        "are the ones most likely to land here",
    ),
}

#: What an unregistered profile gets. Same as `generic` — an unknown genre is
#: exactly as informative as no genre.
DEFAULT_PRIOR = PRIORS["generic"]


def genre_prior(profile) -> GenrePrior:
    """The prior for a profile, its name, or ``None``."""
    name = getattr(profile, "name", profile) or "generic"
    prior = PRIORS.get(str(name))
    if prior is not None:
        return prior
    return GenrePrior(str(name), DEFAULT_PRIOR.p_norma, DEFAULT_PRIOR.note)
