
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import time
import os
import json
from scipy import stats
from IPython.display import display

sns.set_theme(style='whitegrid')
plt.rcParams['figure.figsize'] = (12, 6)

BASE_URL = 'https://pokeapi.co/api/v2/'
CACHE_DIR = 'pokeapi_cache'
os.makedirs(CACHE_DIR, exist_ok=True)

print('Bibliotheques chargees avec succes !')
pokemon_data = []
session = requests.Session()
for generation in range(1,10):
    print(f'Recuperation generation {generation}...')
    url=f'{BASE_URL}generation/{generation}/'
    response = session.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    for species in data['pokemon_species']:
        response = session.get(species['url'], timeout=30)
        response.raise_for_status()
        species_data = response.json()
        for varieties in species_data['varieties']:
            response = session.get(varieties['pokemon']['url'], timeout=30)
            response.raise_for_status()
            varieties_data = response.json()
            row ={'name':varieties['pokemon']['name'],'is_default':varieties['is_default'],'generation':generation,'is_legendary': species_data['is_legendary'],
            'is_mythical': species_data['is_mythical']}
            for stat in varieties_data['stats']:
                row[stat['stat']['name']] = stat['base_stat']
            pokemon_data.append(row)
        
df = pd.DataFrame(pokemon_data)
#df = df.drop_duplicates(subset='id').reset_index(drop=True)
print('\nCollecte terminee !')
print('Nombre de Pokemon :', len(df))
display(df.head())

# Dossier de destination
CACHE_DIR = "data"

# Nom du fichier
filename = os.path.join(CACHE_DIR, "PokeAPIData.parquet")

# Créer le dossier s'il n'existe pas
os.makedirs(CACHE_DIR, exist_ok=True)

# Enregistrer le DataFrame au format Parquet
df.to_parquet(filename, index=False)
#pour lire le fichier df = pd.read_parquet(filename)
"""
species= data['pokemon_species'][0]
response = session.get(species['url'], timeout=30)
response.raise_for_status()
species_data = response.json()
#print(species_data['varieties'])
variety=species_data['varieties'][0]
response = session.get(variety['pokemon']['url'], timeout=30)
response.raise_for_status()
varieties_data = response.json()
print(varieties_data['stats'])"""