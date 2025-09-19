import pandas as pd
import os
from datetime import datetime

CSV_PATH = "data/data.csv"

def cargar_o_crear_dataframe():
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        print("✅ CSV cargado.")
    else:
        df = pd.DataFrame(columns=["value", "date"])
        print("📄 CSV no encontrado. Creando uno nuevo.")
    return df

def añadir_fila(df):
    nueva_fila = {
        "value": 143.23,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")  
    }
    return pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)

def guardar_dataframe(df):
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"💾 CSV guardado en {CSV_PATH}")
