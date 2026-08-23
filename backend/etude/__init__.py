"""Instrumentation de l'etude MARC.

Ce paquet contient TOUT ce qui sert a mesurer, et rien qui serve a produire le
compte rendu. La separation est volontaire : le jour ou l'etude s'arrete, ce
paquet se retire sans toucher au moteur.

Reference : docs/specs/spec/MARC_cahier_de_recueil.md (sections 7 et 8).

  models.py    les tables : session, dossier, prelevement, proposition,
               question, pause, reponse de questionnaire
  vocabulaire.py  les valeurs autorisees (types, decisions, motifs)
"""
