# agent/feriados_municipais.py — Feriados municipais de Portugal Continental
# Generado por AgentKit

"""
Feriados municipais (facultativos) dos 278 concelhos de Portugal
Continental — excluem-se Açores e Madeira. Compilados e cruzados a
partir de fontes agregadoras públicas (icalendario.pt, dirportugal.com),
verificados em 2026/2027/2028 para separar datas fixas de datas móveis.

Estes feriados são definidos por postura de cada câmara municipal e
podem mudar — se um valor aqui parecer desatualizado, confirmar junto
da câmara municipal do concelho em causa antes de confiar cegamente.
"""

# concelho -> (mes, dia), para feriados municipais de data fixa
FERIADOS_MUNICIPAIS_FIXOS: dict[str, tuple[int, int]] = {
    # --- Aveiro ---
    "Albergaria-a-Velha": (8, 17),
    "Arouca": (5, 2),
    "Aveiro": (5, 12),
    "Castelo de Paiva": (6, 24),
    "Espinho": (6, 16),
    "Estarreja": (6, 13),
    "Murtosa": (9, 8),
    "Oliveira de Azeméis": (8, 10),
    "Ovar": (7, 25),
    "Santa Maria da Feira": (1, 20),
    "São João da Madeira": (10, 11),
    "Sever do Vouga": (9, 21),
    "Vale de Cambra": (6, 13),

    # --- Beja ---
    "Aljustrel": (6, 13),
    "Almodôvar": (6, 24),
    "Barrancos": (8, 28),
    "Castro Verde": (6, 29),
    "Ferreira do Alentejo": (3, 5),
    "Mértola": (6, 24),
    "Moura": (6, 24),
    "Odemira": (9, 8),
    "Ourique": (9, 8),

    # --- Braga ---
    "Amares": (6, 13),
    "Barcelos": (5, 3),
    "Braga": (6, 24),
    "Cabeceiras de Basto": (9, 29),
    "Celorico de Basto": (7, 25),
    "Esposende": (8, 19),
    "Fafe": (5, 16),
    "Guimarães": (6, 24),
    "Póvoa de Lanhoso": (3, 19),
    "Terras de Bouro": (10, 20),
    "Vieira do Minho": (10, 5),
    "Vila Nova de Famalicão": (6, 13),
    "Vila Verde": (6, 13),
    "Vizela": (3, 19),

    # --- Bragança ---
    "Alfândega da Fé": (6, 29),
    "Bragança": (8, 22),
    "Carrazeda de Ansiães": (8, 31),
    "Macedo de Cavaleiros": (6, 29),
    "Miranda do Douro": (7, 10),
    "Mirandela": (5, 25),
    "Mogadouro": (10, 15),
    "Torre de Moncorvo": (3, 19),
    "Vila Flor": (8, 24),
    "Vimioso": (8, 10),
    "Vinhais": (5, 20),

    # --- Castelo Branco ---
    "Belmonte": (4, 26),
    "Covilhã": (10, 20),
    "Fundão": (9, 15),
    "Oleiros": (8, 10),
    "Proença-a-Nova": (6, 13),
    "Sertã": (6, 24),
    "Vila de Rei": (9, 19),
    "Vila Velha de Ródão": (8, 24),

    # --- Coimbra ---
    "Arganil": (9, 7),
    "Cantanhede": (7, 25),
    "Coimbra": (7, 4),
    "Condeixa-a-Nova": (7, 24),
    "Figueira da Foz": (6, 24),
    "Góis": (8, 13),
    "Lousã": (6, 24),
    "Mira": (7, 25),
    "Miranda do Corvo": (6, 1),
    "Montemor-o-Velho": (9, 8),
    "Oliveira do Hospital": (10, 7),
    "Pampilhosa da Serra": (4, 10),
    "Penacova": (7, 17),
    "Penela": (9, 29),
    "Soure": (9, 21),
    "Tábua": (4, 10),
    "Vila Nova de Poiares": (1, 13),

    # --- Évora ---
    "Évora": (6, 29),
    "Montemor-o-Novo": (3, 8),
    "Mourão": (2, 2),
    "Reguengos de Monsaraz": (6, 13),
    "Vendas Novas": (9, 7),
    "Viana do Alentejo": (1, 13),
    "Vila Viçosa": (8, 16),

    # --- Faro ---
    "Albufeira": (8, 20),
    "Alcoutim": (9, 11),
    "Aljezur": (8, 29),
    "Castro Marim": (6, 24),
    "Faro": (9, 7),
    "Lagoa": (9, 8),
    "Lagos": (10, 27),
    "Olhão": (6, 16),
    "Portimão": (12, 11),
    "São Brás de Alportel": (6, 1),
    "Silves": (9, 3),
    "Tavira": (6, 24),
    "Vila do Bispo": (1, 22),
    "Vila Real de Santo António": (5, 13),

    # --- Guarda ---
    "Aguiar da Beira": (2, 10),
    "Almeida": (7, 2),
    "Celorico da Beira": (5, 23),
    "Figueira de Castelo Rodrigo": (7, 7),
    "Fornos de Algodres": (9, 29),
    "Gouveia": (8, 10),
    "Guarda": (11, 27),
    "Manteigas": (3, 4),
    "Mêda": (11, 11),
    "Pinhel": (8, 25),
    "Seia": (7, 3),
    "Trancoso": (5, 29),
    "Vila Nova de Foz Côa": (5, 21),

    # --- Leiria ---
    "Alcobaça": (8, 20),
    "Alvaiázere": (6, 13),
    "Batalha": (8, 14),
    "Bombarral": (6, 29),
    "Caldas da Rainha": (5, 15),
    "Castanheira de Pera": (7, 4),
    "Figueiró dos Vinhos": (6, 24),
    "Leiria": (5, 22),
    "Nazaré": (9, 8),
    "Óbidos": (1, 11),
    "Pedrógão Grande": (7, 24),
    "Peniche": (8, 3),
    "Pombal": (11, 11),
    "Porto de Mós": (6, 29),

    # --- Lisboa ---
    "Amadora": (9, 11),
    "Cadaval": (1, 13),
    "Cascais": (6, 13),
    "Lisboa": (6, 13),
    "Loures": (7, 26),
    "Lourinhã": (6, 24),
    "Odivelas": (11, 19),
    "Oeiras": (6, 7),
    "Sintra": (6, 29),
    "Torres Vedras": (11, 11),

    # --- Portalegre ---
    "Arronches": (6, 24),
    "Elvas": (1, 14),
    "Fronteira": (4, 6),
    "Gavião": (11, 23),
    "Marvão": (9, 8),
    "Portalegre": (5, 23),

    # --- Porto ---
    "Amarante": (7, 8),
    "Baião": (8, 24),
    "Felgueiras": (6, 29),
    "Gondomar": (10, 5),
    "Lousada": (7, 27),
    "Maia": (7, 13),
    "Marco de Canaveses": (9, 8),
    "Paços de Ferreira": (11, 6),
    "Paredes": (7, 20),
    "Penafiel": (11, 11),
    "Porto": (6, 24),
    "Póvoa de Varzim": (6, 29),
    "Santo Tirso": (7, 11),
    "Trofa": (11, 19),
    "Valongo": (6, 24),
    "Vila do Conde": (6, 24),
    "Vila Nova de Gaia": (6, 24),

    # --- Santarém ---
    "Abrantes": (6, 14),
    "Alpiarça": (4, 2),
    "Coruche": (8, 17),
    "Entroncamento": (11, 24),
    "Ferreira do Zêzere": (6, 13),
    "Ourém": (6, 20),
    "Rio Maior": (11, 6),
    "Santarém": (3, 19),
    "Sardoal": (9, 22),
    "Tomar": (3, 1),
    "Vila Nova da Barquinha": (6, 13),

    # --- Setúbal ---
    "Alcácer do Sal": (6, 24),
    "Alcochete": (6, 24),
    "Almada": (6, 24),
    "Barreiro": (6, 28),
    "Grândola": (10, 22),
    "Moita": (9, 15),
    "Montijo": (6, 29),
    "Palmela": (6, 1),
    "Santiago do Cacém": (7, 25),
    "Seixal": (6, 29),
    "Sesimbra": (5, 4),
    "Setúbal": (9, 15),
    "Sines": (11, 24),

    # --- Viana do Castelo ---
    "Arcos de Valdevez": (7, 11),
    "Monção": (3, 12),
    "Paredes de Coura": (8, 10),
    "Ponte da Barca": (8, 24),
    "Ponte de Lima": (9, 20),
    "Valença": (2, 18),
    "Viana do Castelo": (8, 20),
    "Vila Nova de Cerveira": (10, 1),

    # --- Vila Real ---
    "Alijó": (11, 11),
    "Boticas": (11, 6),
    "Chaves": (7, 8),
    "Mesão Frio": (11, 30),
    "Mondim de Basto": (7, 25),
    "Montalegre": (6, 9),
    "Murça": (5, 8),
    "Peso da Régua": (8, 16),
    "Ribeira de Pena": (8, 16),
    "Sabrosa": (9, 8),
    "Santa Marta de Penaguião": (1, 13),
    "Valpaços": (11, 6),
    "Vila Pouca de Aguiar": (6, 22),
    "Vila Real": (6, 13),

    # --- Viseu ---
    "Armamar": (6, 24),
    "Carregal do Sal": (7, 20),
    "Castro Daire": (6, 29),
    "Cinfães": (6, 24),
    "Lamego": (9, 8),
    "Mangualde": (9, 8),
    "Moimenta da Beira": (6, 24),
    "Nelas": (6, 24),
    "Oliveira de Frades": (10, 7),
    "Penalva do Castelo": (8, 25),
    "Penedono": (6, 29),
    "Resende": (9, 29),
    "São João da Pesqueira": (6, 24),
    "São Pedro do Sul": (6, 29),
    "Sátão": (8, 20),
    "Sernancelhe": (5, 3),
    "Tabuaço": (6, 24),
    "Tarouca": (9, 29),
    "Tondela": (9, 16),
    "Vila Nova de Paiva": (3, 2),
    "Viseu": (9, 21),
    "Vouzela": (5, 14),
}

# concelho -> regra móvel, resolvida em relação ao Domingo de Páscoa
# pascoa+1  = Segunda-feira de Páscoa
# pascoa+2  = Terça-feira de Páscoa
# pascoa+8  = Segunda-feira de Pascoela
# pascoa+15 = segunda-feira da 2ª semana depois da Páscoa
# pascoa+39 = Quinta-feira da Ascensão
# pascoa+50 = Segunda-feira de Pentecostes
# pascoa+51 = Terça-feira de Pentecostes
FERIADOS_MUNICIPAIS_MOVEIS: dict[str, str] = {
    # --- pascoa+1 (Segunda-feira de Páscoa) ---
    "Ílhavo": "pascoa+1",
    "Cuba": "pascoa+1",
    "Freixo de Espada à Cinta": "pascoa+1",
    "Penamacor": "pascoa+1",
    "Borba": "pascoa+1",
    "Mora": "pascoa+1",
    "Portel": "pascoa+1",
    "Redondo": "pascoa+1",
    "Avis": "pascoa+1",
    "Campo Maior": "pascoa+1",
    "Castelo de Vide": "pascoa+1",
    "Crato": "pascoa+1",
    "Nisa": "pascoa+1",
    "Ponte de Sor": "pascoa+1",
    "Sousel": "pascoa+1",
    "Constância": "pascoa+1",
    "Mação": "pascoa+1",
    "Caminha": "pascoa+1",

    # --- pascoa+2 (Terça-feira de Páscoa) ---
    "Serpa": "pascoa+2",
    "Castelo Branco": "pascoa+2",

    # --- pascoa+8 (Segunda-feira de Pascoela) ---
    "Alandroal": "pascoa+8",
    "Sabugal": "pascoa+8",
    "Monforte": "pascoa+8",

    # --- pascoa+15 ---
    "Idanha-a-Nova": "pascoa+15",

    # --- pascoa+39 (Quinta-feira da Ascensão) ---
    "Anadia": "pascoa+39",
    "Mealhada": "pascoa+39",
    "Oliveira do Bairro": "pascoa+39",
    "Alvito": "pascoa+39",
    "Beja": "pascoa+39",
    "Vidigueira": "pascoa+39",
    "Arraiolos": "pascoa+39",
    "Estremoz": "pascoa+39",
    "Loulé": "pascoa+39",
    "Monchique": "pascoa+39",
    "Ansião": "pascoa+39",
    "Marinha Grande": "pascoa+39",
    "Alenquer": "pascoa+39",
    "Arruda dos Vinhos": "pascoa+39",
    "Azambuja": "pascoa+39",
    "Mafra": "pascoa+39",
    "Sobral de Monte Agraço": "pascoa+39",
    "Vila Franca de Xira": "pascoa+39",
    "Alter do Chão": "pascoa+39",
    "Alcanena": "pascoa+39",
    "Almeirim": "pascoa+39",
    "Benavente": "pascoa+39",
    "Cartaxo": "pascoa+39",
    "Chamusca": "pascoa+39",
    "Golegã": "pascoa+39",
    "Salvaterra de Magos": "pascoa+39",
    "Torres Novas": "pascoa+39",
    "Melgaço": "pascoa+39",
    "Mortágua": "pascoa+39",
    "Santa Comba Dão": "pascoa+39",

    # --- pascoa+50 (Segunda-feira de Pentecostes) ---
    "Águeda": "pascoa+50",
    "Vagos": "pascoa+50",

    # --- pascoa+51 (Terça-feira de Pentecostes) ---
    "Matosinhos": "pascoa+51",
}
