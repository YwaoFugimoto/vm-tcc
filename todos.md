### TODO' s

- Trafira por ssh o arquivo ´formulas_unicas.txt´

- Transformar todo o processamento dos dados em um unico arquivo, pipeline

    - 1: Extrair a formula
    - 2: Limpar a formula
    - 3: indexar a formula
    - 4: criar index no elasticsearch
        - docker-compose = ´/home/default/kibana-tcc/mathseek/back-end/docker-compose.yml´

    - 5: Processamento das formulas
        - DIRECT:
            - Faz embedding da formula (embedding-service - python)
            - Indexa


        

        - TOKENIXZED:
            - Tokenzina formula (api - java)
            - Faz embedding para cada Token (embedding-service - python)
            - Calcula media dos embeddings (api-media - python)
            - Indexa


    - 6: bulk no elastic para ambos os indices
    

    - Uma formula normal sera inputada e deve ser processada ate chegar no elasticsearch, estando anexada aos dois indices.
