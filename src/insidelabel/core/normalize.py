"""Ingredient normalization."""

def normalize(token, synonym_lookup):
    """Return canonical form of a token via synonym table."""
    if token in synonym_lookup:
        return synonym_lookup[token]
    return token
