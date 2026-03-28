# ELASTICSEARCH MAPPIGNS



´´´
PUT /formulas_embedding
{
  "settings": {

    "number_of_shards": "1",
    "number_of_replicas": "0"
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword",

            "ignore_above": 256
          }
        }
      },
      "formula": {
        "type": "text"
      },
      "formula_embedding": {
        "type": "dense_vector",
        "dims": 384,
        "index": "true",
        "similarity": "cosine",
        "index_options": {

          "type": "hnsw",
          "m": 16,
          "ef_construction": 100

        }
      }

    }
  }

}


PUT /formulas_token_embedding_avg
{

  "settings": {
    "number_of_shards": "1",
    "number_of_replicas": "0"
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {

            "type": "keyword",
            "ignore_above": 256
          }
        }

      },
      "formula": {
        "type": "text"
      },
      "token_list": {
        "type": "text"
      },
        <!--Modified to "token_average_embedding"-->
      "token_embedding": {

        "type": "dense_vector",

        "dims": 384,
        "index": "true",
        "similarity": "cosine",
        "index_options": {
          "type": "hnsw",
          "m": 16,
          "ef_construction": 100
        }

      }
    }
  }
}
´´´
