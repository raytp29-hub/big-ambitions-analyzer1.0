"""
core/schema_utils.py
Validazione condivisa degli schemi DataFrame.

Estratto da data_loader.py quando è arrivato core/snapshot.py: entrambi i
moduli devono validare i loro DataFrame, e tenere la funzione in un modulo
terzo evita l'import circolare (data_loader importa snapshot per costruire
il bundle, quindi snapshot non può importare data_loader).
"""

import pandas as pd


def validate_df(df: pd.DataFrame, name: str, schema: dict[str, str]) -> None:
    """
    Alza ValueError se df non ha esattamente le colonne dello schema
    o se un dtype non combacia. `name` serve solo per il messaggio d'errore.
    """
    got = set(df.columns)
    want = set(schema)
    if got != want:
        missing = want - got
        extra = got - want
        raise ValueError(f"{name}: missing {missing}, extra {extra}")

    for col, want_dtype in schema.items():
        got_dtype = str(df[col].dtype)
        if got_dtype != want_dtype:
            raise ValueError(
                f"{name}.{col}: expected dtype {want_dtype!r}, got {got_dtype!r}"
            )
