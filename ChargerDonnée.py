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
#On peut utiliser cet fonction pour charger les données
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