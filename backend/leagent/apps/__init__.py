"""Per-service runtime entrypoints.

Each sub-package is a standalone service built on top of :mod:`leagent_core`
plus whichever ``leagent`` modules implement its business logic. During the
phased migration they import heavily from the existing monolith; long-term
they will vendor only what they need.
"""
