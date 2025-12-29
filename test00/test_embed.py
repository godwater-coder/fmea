# quick test to create an embedding using langchain_openai's OpenAIEmbeddings
from dotenv import load_dotenv
from os import getenv
import os
from langchain_openai import OpenAIEmbeddings

load_dotenv()
API_KEY = getenv('OPENAI_API_KEY')
if not API_KEY:
    print('No OPENAI_API_KEY in environment')
    raise SystemExit(1)

os.environ['OPENAI_API_KEY'] = API_KEY
model = getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')
print('Using embedding model:', model)
emb = OpenAIEmbeddings(model=model)
vec = emb.embed_query('hello world')
print('Embedding length:', len(vec))
print('First 5 dims:', vec[:5])
