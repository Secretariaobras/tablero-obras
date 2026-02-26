import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

ALCANCES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

ruta_json = os.getenv("RUTA_GOOGLE_JSON")

credenciales = Credentials.from_service_account_file(
    ruta_json, 
    scopes=ALCANCES
)