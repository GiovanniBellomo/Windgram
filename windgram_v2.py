#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windgram_v2.py -- lanciatore sottile della dashboard windgram.

Mantiene invariata l'invocazione abituale `py windgram_v2.py --lat ...`: tutta
l'orchestrazione vera vive nel package (`windgram.cli`, Fase G1 del refactoring
a strati -- vedi REFACTOR.md). Equivalente: `py -m windgram.cli ...`.
"""
from windgram.cli import main

if __name__ == "__main__":
    main()
