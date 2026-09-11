"""Localization resolver for Big Ambitions display names and help text.

Reads the game's locale JSON files (data/locales/<lang>.json) and exposes
a single accessor: display_name(key, lang).

Perché esiste questo modulo
---------------------------
Prima: mappe hardcoded tipo {"pizza": "Pizza"} sparse nelle pagine Streamlit.
Quando il gioco aggiorna un nome, tocca cacciarle una per una.

Dopo: puntiamo direttamente ai file di localizzazione che il gioco già
consuma. Si aggiornano da soli con il gioco e otteniamo 24 lingue "gratis"
(en, it, de, fr, es, ja, ...).

Sorgente dei dati
-----------------
    <game>/Big Ambitions_Data/StreamingAssets/locale/<lang>.json

Copiare en.json (e ogni altra lingua che ci serve) in data/locales/ del repo.
NB: cartella di gioco = 'locale' (minuscolo, singolare), non 'Locales'.

Formato delle chiavi (build ~3540)
----------------------------------
Dict piatto str -> str, ~6036 chiavi per lingua. Prefissi principali:
    ba:itemname_<slug>        831 nomi item      ("ba:itemname_pizza" -> "Pizza")
    ba:businesstype_<slug>     47 tipi business  ("ba:businesstype_giftshop" -> "Gift Shop")
    help_ba:itemname_<slug>_content   670 help pages markdown per item
    common_<x>                204 stringhe UI comuni
    bizman_, dialog_, tutorial_, ...  UI specifiche
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# Cartella che contiene i file JSON di localizzazione.
# Path calcolato relativo a QUESTO file, non alla cwd, così funziona
# indipendentemente da dove Streamlit viene lanciato.
#   __file__                       -> .../big-ambition-analyzer/core/localization.py
#   .resolve().parent              -> .../big-ambition-analyzer/core/
#   .resolve().parent.parent       -> .../big-ambition-analyzer/
#   .../data/locales/              -> data statici di localizzazione
_LOCALES_DIR = Path(__file__).resolve().parent.parent / "data" / "locales"


@lru_cache(maxsize=None)
def _load(lang: str) -> dict[str, str]:
    """Load and cache one locale file.

    Cached perché il file è ~800KB e Streamlit ri-esegue lo script a ogni
    interazione utente: senza cache si ri-parserebbe il JSON N volte al minuto.

    Con @lru_cache il file viene letto e parsato una sola volta per lingua per
    processo, poi il dict resta in memoria (ordine ~1-2 MB per lingua).
    maxsize=None = nessun limite; tanto le lingue sono max 24, trascurabile.

    Perché una funzione separata invece di caricare a module-level:
        - lazy: il file viene letto SOLO se qualcuno chiama display_name(),
          non all'import (evita costi se il modulo viene importato ma non usato)
        - testable: si può monkey-patch _load per iniettare dati di test
        - multi-lang: la cache tiene una entry per lingua, senza logica manuale
    """
    path = _LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Locale file not found: {path}. "
            f"Copiare <game>/Big Ambitions_Data/StreamingAssets/locale/{lang}.json "
            f"in data/locales/ del repo."
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def display_name(key: str, lang: str = "en", default: str | None = None) -> str:
    """Risolve una chiave di localizzazione nella sua stringa visualizzabile.

    Args:
        key: chiave del file di localizzazione, es. "ba:itemname_pizza".
        lang: codice lingua a due lettere corrispondente a un file in
            data/locales/. Default "en".
        default: valore restituito se la chiave non esiste nel file.
            Se None (default), viene restituita la chiave stessa: così
            un mismatch è visibile subito nella UI senza far crashare
            il tool. Passare "" o una stringa esplicita se si preferisce
            un fallback silenzioso.

    Returns:
        La stringa localizzata, oppure il default, oppure la chiave.

    Examples:
        >>> display_name("ba:itemname_pizza")
        'Pizza'
        >>> display_name("ba:businesstype_giftshop")
        'Gift Shop'
        >>> display_name("chiave_inesistente")            # fallback = chiave
        'chiave_inesistente'
        >>> display_name("chiave_inesistente", default="?")
        '?'
    """
    data = _load(lang)
    if default is None:
        return data.get(key, key)
    return data.get(key, default)
