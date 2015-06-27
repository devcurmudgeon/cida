# cida

cida is an experimental integration of ybd with the three repos that Baserock has published for 'morphologies' over the years.

The aim is to explore the cost/benefit of integrating the tooling with the definitions, and maybe having a wrangler step to convert formats+versions of manifests into a normalised representation which can be integrated generically (and optionally deployed).

The repo was created as a set of git subtrees - the actual commands are in [startup.sh](scripts/startup.sh)

If this approach proves interesting, we could look at doing the same for other kinds of recipes/manifests.
