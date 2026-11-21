
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
'''
session = requests.Session()


def get_api(url):
    filename = os.path.join(CACHE_DIR, str(abs(hash(url))) + '.json')

    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)

    response = session.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    time.sleep(0.05)
    return data


pokemon_data = []

for generation in range(1, 10):
    print(f'Recuperation generation {generation}...')

    gen_data = get_api(f'{BASE_URL}generation/{generation}/')

    for species in gen_data['pokemon_species']:
        species_data = get_api(species['url'])

        default_variety = next(
            (v for v in species_data['varieties'] if v['is_default']),
            None
        )

        if default_variety is None:
            continue

        pokemon = get_api(default_variety['pokemon']['url'])

        row = {
            'id': species_data['id'],
            'name': species_data['name'],
            'generation': generation,
            'is_legendary': species_data['is_legendary'],
            'is_mythical': species_data['is_mythical'],
            'types': ', '.join(t['type']['name'] for t in pokemon['types'])
        }

        for stat in pokemon['stats']:
            row[stat['stat']['name']] = stat['base_stat']

        pokemon_data.append(row)


df = pd.DataFrame(pokemon_data)
df = df.drop_duplicates(subset='id').reset_index(drop=True)

print('\nCollecte terminee !')
print('Nombre de Pokemon :', len(df))
display(df.head())'''
pokemon_data = []
session = requests.Session()
for generation in range(1,2):
    print(f'Recuperation generation {generation}...')
    url=f'{BASE_URL}generation/{generation}/'
    response = session.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    for species in data['pokemon_species'][0:5]:
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