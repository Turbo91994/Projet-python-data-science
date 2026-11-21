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
import s3fs

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
#extrait du SSP cloud le data frame de PokeAPI
def SSPRead(): 
    #Initialisation File system
    S3_ENDPOINT_URL = "https://" + os.environ["AWS_S3_ENDPOINT"]
    fs = s3fs.S3FileSystem(client_kwargs={'endpoint_url': S3_ENDPOINT_URL})
    BUCKET = "partigue"
    FILE_KEY_S3 = "diffusion/PokeAPI.parquet"
    FILE_PATH_S3 = BUCKET + "/" + FILE_KEY_S3
    with fs.open(FILE_PATH_S3, mode="rb") as file_in:
        df = pd.read_parquet(file_in)
    return df
# enregistre le data frame extrait de PokeAPI dans SSP Cloud
def SSPWrite(df):
    #Initialisation File system
    S3_ENDPOINT_URL = "https://" + os.environ["AWS_S3_ENDPOINT"]
    fs = s3fs.S3FileSystem(client_kwargs={'endpoint_url': S3_ENDPOINT_URL})
    BUCKET_OUT = "partigue"
    FILE_KEY_OUT_S3 = "diffusion/PokeAPI.parquet"
    FILE_PATH_OUT_S3 = BUCKET_OUT + "/" + FILE_KEY_OUT_S3
    with fs.open(FILE_PATH_OUT_S3, 'wb') as file_out:
        df.to_parquet(file_out, index=False)

#SSPWrite(df)