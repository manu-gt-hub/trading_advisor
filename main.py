import os

# Acceder al secret desde la variable de entorno
my_secret = os.getenv("SECRET_TEST")

# Imprimir el valor (en producción, evita imprimir secretos)
print(f"El secret es: {my_secret}")
