MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def local_encoder(texts):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL, device="cpu").encode(list(texts), normalize_embeddings=True)
