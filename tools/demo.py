"""Carpeta de datos de demostración para las capturas del README: títulos famosos con fechas y notas inventadas.

Nunca usa tus datos: lo escribe todo en la carpeta que le digas (vacía), con un .env propio cuyas carpetas de exports
apuntan solo a un export de Letterboxd de mentira que crea ahí mismo, y claves falsas. Las estadísticas se calculan
con el código de la app (core/estadisticas.py) a partir de fichas escritas a mano, sin conectarse a nada.

    python -m tools.demo <carpeta>            # crea la demo
    set TRISYNC_DATOS=<carpeta> && python sync.py --puerto 8772   # la abre (no pulses Revisar: las claves son falsas)
"""
import csv
import json
import os
import random
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ, UTC = ZoneInfo("Europe/Madrid"), ZoneInfo("UTC")
HOY = date(2026, 11, 16)  # último día con datos (fijo: la demo sale siempre igual)
REVISION = "16/11/2026 21:04"

# ---------------- películas ----------------
# título|año|país|géneros|dirección|reparto|estudio|saga|idioma|min|IMDb|miles de votos|coste M$|taquilla M$|tu nota|♥
PELIS = """
The Matrix|1999|US|Action,Science Fiction|Lana Wachowski,Lilly Wachowski|Keanu Reeves,Laurence Fishburne,Carrie-Anne Moss|Warner Bros. Pictures|The Matrix Collection|en|136|8.7|2100|63|467|10|1
The Matrix Reloaded|2003|US|Action,Science Fiction|Lana Wachowski,Lilly Wachowski|Keanu Reeves,Laurence Fishburne,Carrie-Anne Moss|Warner Bros. Pictures|The Matrix Collection|en|138|7.2|640|150|741|7|0
Inception|2010|US|Action,Science Fiction,Thriller|Christopher Nolan|Leonardo DiCaprio,Joseph Gordon-Levitt,Elliot Page|Warner Bros. Pictures||en|148|8.8|2600|160|836|9|1
Interstellar|2014|US|Adventure,Drama,Science Fiction|Christopher Nolan|Matthew McConaughey,Anne Hathaway,Jessica Chastain|Paramount Pictures||en|169|8.7|2300|165|732|10|1
The Dark Knight|2008|US|Action,Crime,Drama|Christopher Nolan|Christian Bale,Heath Ledger,Aaron Eckhart|Warner Bros. Pictures|The Dark Knight Collection|en|152|9.0|3000|185|1006|10|1
Batman Begins|2005|US|Action,Crime,Drama|Christopher Nolan|Christian Bale,Michael Caine,Liam Neeson|Warner Bros. Pictures|The Dark Knight Collection|en|140|8.2|1600|150|373|8|0
Oppenheimer|2023|US|Drama,History|Christopher Nolan|Cillian Murphy,Emily Blunt,Matt Damon|Universal Pictures||en|181|8.3|900|100|975|9|0
Memento|2000|US|Mystery,Thriller|Christopher Nolan|Guy Pearce,Carrie-Anne Moss,Joe Pantoliano|Summit Entertainment||en|113|8.4|1300|9|40|8|0
Pulp Fiction|1994|US|Thriller,Crime|Quentin Tarantino|John Travolta,Uma Thurman,Samuel L. Jackson|Miramax||en|154|8.9|2300|8|214|9|1
Django Unchained|2012|US|Drama,Western|Quentin Tarantino|Jamie Foxx,Christoph Waltz,Leonardo DiCaprio|Columbia Pictures||en|165|8.5|1700|100|426|8|0
Inglourious Basterds|2009|US|Drama,Thriller,War|Quentin Tarantino|Brad Pitt,Christoph Waltz,Mélanie Laurent|Universal Pictures||en|153|8.4|1600|70|321|9|0
Once Upon a Time in Hollywood|2019|US|Comedy,Drama|Quentin Tarantino|Leonardo DiCaprio,Brad Pitt,Margot Robbie|Columbia Pictures||en|161|7.6|900|90|377|7|0
Parasite|2019|KR|Comedy,Thriller,Drama|Bong Joon-ho|Song Kang-ho,Lee Sun-kyun,Cho Yeo-jeong|CJ Entertainment||ko|133|8.5|1000|11|262|10|1
Memories of Murder|2003|KR|Crime,Drama,Thriller|Bong Joon-ho|Song Kang-ho,Kim Sang-kyung|CJ Entertainment||ko|132|8.1|230|2.8||9|0
Oldboy|2003|KR|Drama,Thriller,Mystery|Park Chan-wook|Choi Min-sik,Yoo Ji-tae,Kang Hye-jung|Show East||ko|120|8.3|640|3|15|8|0
Spirited Away|2001|JP|Animation,Family,Fantasy|Hayao Miyazaki|Rumi Hiiragi,Miyu Irino,Mari Natsuki|Studio Ghibli||ja|125|8.6|900|19|395|10|1
My Neighbor Totoro|1988|JP|Animation,Family,Fantasy|Hayao Miyazaki|Noriko Hidaka,Chika Sakamoto|Studio Ghibli||ja|86|8.1|400|3.7|41|9|0
Princess Mononoke|1997|JP|Animation,Adventure,Fantasy|Hayao Miyazaki|Yoji Matsuda,Yuriko Ishida|Studio Ghibli||ja|134|8.3|450|23.5|170|9|0
Your Name.|2016|JP|Animation,Romance,Drama|Makoto Shinkai|Ryunosuke Kamiki,Mone Kamishiraishi|CoMix Wave Films||ja|106|8.4|330||382|9|0
Amélie|2001|FR|Comedy,Romance|Jean-Pierre Jeunet|Audrey Tautou,Mathieu Kassovitz|UGC||fr|122|8.3|800|10|174|8|0
The Intouchables|2011|FR|Drama,Comedy|Olivier Nakache,Éric Toledano|François Cluzet,Omar Sy|Gaumont||fr|112|8.5|950|9.5|426|8|0
Portrait of a Lady on Fire|2019|FR|Drama,Romance,History|Céline Sciamma|Noémie Merlant,Adèle Haenel|Lilies Films||fr|122|8.1|120|||9|0
Pan's Labyrinth|2006|ES|Fantasy,Drama,War|Guillermo del Toro|Ivana Baquero,Sergi López,Maribel Verdú|Estudios Picasso||es|118|8.2|720|19|83|9|0
The Secret in Their Eyes|2009|AR|Crime,Drama,Mystery|Juan José Campanella|Ricardo Darín,Soledad Villamil|Tornasol Films||es|129|8.2|220|2|34|9|0
Wild Tales|2014|AR|Comedy,Drama,Thriller|Damián Szifron|Ricardo Darín,Érica Rivas,Leonardo Sbaraglia|El Deseo||es|122|8.1|220|3.3|31|8|0
The Others|2001|ES|Horror,Mystery|Alejandro Amenábar|Nicole Kidman,Fionnula Flanagan|Sogecine||en|101|7.6|400|17|210|8|0
Open Your Eyes|1997|ES|Drama,Mystery,Science Fiction|Alejandro Amenábar|Eduardo Noriega,Penélope Cruz|Sogecine||es|117|7.7|70|||8|0
Volver|2006|ES|Comedy,Drama|Pedro Almodóvar|Penélope Cruz,Carmen Maura,Lola Dueñas|El Deseo||es|121|7.6|100|9.4|87|8|0
Cinema Paradiso|1988|IT|Drama,Romance|Giuseppe Tornatore|Philippe Noiret,Salvatore Cascio|Cristaldifilm||it|155|8.5|290|||10|1
Life Is Beautiful|1997|IT|Comedy,Drama|Roberto Benigni|Roberto Benigni,Nicoletta Braschi|Melampo Cinematografica||it|116|8.6|750|20|230|9|0
The Lives of Others|2006|DE|Drama,Thriller|Florian Henckel von Donnersmarck|Ulrich Mühe,Sebastian Koch,Martina Gedeck|Wiedemann & Berg||de|137|8.4|410|2|77|9|0
Run Lola Run|1998|DE|Action,Thriller|Tom Tykwer|Franka Potente,Moritz Bleibtreu|X Filme Creative Pool||de|81|7.6|210|||7|0
City of God|2002|BR|Drama,Crime|Fernando Meirelles|Alexandre Rodrigues,Leandro Firmino|O2 Filmes||pt|130|8.6|800|3.3|30|9|0
Amores perros|2000|MX|Drama,Thriller|Alejandro G. Iñárritu|Gael García Bernal,Emilio Echevarría|Altavista Films||es|154|8.0|250|2.4|20|8|0
Y tu mamá también|2001|MX|Drama,Romance|Alfonso Cuarón|Gael García Bernal,Diego Luna,Maribel Verdú|Anhelo Producciones||es|106|7.6|140|5|33|7|0
Seven Samurai|1954|JP|Action,Drama|Akira Kurosawa|Toshiro Mifune,Takashi Shimura|Toho||ja|207|8.6|370|||9|0
Rashomon|1950|JP|Crime,Drama,Mystery|Akira Kurosawa|Toshiro Mifune,Machiko Kyō,Masayuki Mori|Daiei||ja|88|8.1|180|||8|0
A Separation|2011|IR|Drama|Asghar Farhadi|Peyman Moaadi,Leila Hatami|Asghar Farhadi Productions||fa|123|8.3|260|0.5|22.9|9|0
Drive My Car|2021|JP|Drama|Ryusuke Hamaguchi|Hidetoshi Nishijima,Tōko Miura|Bitters End||ja|179|7.6|60|||8|0
Another Round|2020|DK|Comedy,Drama|Thomas Vinterberg|Mads Mikkelsen,Thomas Bo Larsen|Zentropa||da|117|7.7|190|||8|0
The Hunt|2012|DK|Drama|Thomas Vinterberg|Mads Mikkelsen,Thomas Bo Larsen,Annika Wedderkopp|Zentropa||da|115|8.3|350|3.8|16|9|0
Mad Max: Fury Road|2015|AU|Action,Adventure,Science Fiction|George Miller|Tom Hardy,Charlize Theron,Nicholas Hoult|Warner Bros. Pictures|Mad Max Collection|en|120|8.1|1100|150|380|9|0
The Lord of the Rings: The Fellowship of the Ring|2001|NZ|Adventure,Fantasy,Action|Peter Jackson|Elijah Wood,Ian McKellen,Viggo Mortensen|New Line Cinema|The Lord of the Rings Collection|en|179|8.9|2100|93|898|10|1
The Lord of the Rings: The Two Towers|2002|NZ|Adventure,Fantasy,Action|Peter Jackson|Elijah Wood,Ian McKellen,Viggo Mortensen|New Line Cinema|The Lord of the Rings Collection|en|179|8.8|1900|94|947|9|0
The Lord of the Rings: The Return of the King|2003|NZ|Adventure,Fantasy,Action|Peter Jackson|Elijah Wood,Ian McKellen,Viggo Mortensen|New Line Cinema|The Lord of the Rings Collection|en|201|9.0|2100|94|1146|10|1
Slumdog Millionaire|2008|GB|Drama,Romance|Danny Boyle|Dev Patel,Freida Pinto,Anil Kapoor|Film4||en|120|8.0|900|15|378|7|0
Trainspotting|1996|GB|Drama,Crime|Danny Boyle|Ewan McGregor,Robert Carlyle,Jonny Lee Miller|Film4||en|94|8.1|720|3.5|72|8|0
Paddington|2014|GB|Comedy,Family,Adventure|Paul King|Ben Whishaw,Hugh Bonneville,Sally Hawkins|StudioCanal|Paddington Collection|en|95|7.3|120|55|268|8|0
Paddington 2|2017|GB|Comedy,Family,Adventure|Paul King|Ben Whishaw,Hugh Grant,Hugh Bonneville|StudioCanal|Paddington Collection|en|104|7.8|90|40|227|9|0
Arrival|2016|US|Drama,Science Fiction,Mystery|Denis Villeneuve|Amy Adams,Jeremy Renner,Forest Whitaker|Paramount Pictures||en|116|7.9|800|47|203|9|0
Dune|2021|US|Science Fiction,Adventure|Denis Villeneuve|Timothée Chalamet,Rebecca Ferguson,Oscar Isaac|Legendary Pictures|Dune Collection|en|155|8.0|900|165|407|8|0
Dune: Part Two|2024|US|Science Fiction,Adventure|Denis Villeneuve|Timothée Chalamet,Zendaya,Rebecca Ferguson|Legendary Pictures|Dune Collection|en|166|8.5|600|190|714|9|1
Blade Runner 2049|2017|US|Science Fiction,Drama|Denis Villeneuve|Ryan Gosling,Harrison Ford,Ana de Armas|Alcon Entertainment||en|164|8.0|700|150|259|9|0
Incendies|2010|CA|Drama,Mystery,War|Denis Villeneuve|Lubna Azabal,Mélissa Désormeaux-Poulin|micro_scope||fr|131|8.3|200|6.8|16|9|0
La La Land|2016|US|Comedy,Drama,Romance,Music|Damien Chazelle|Ryan Gosling,Emma Stone,John Legend|Lionsgate||en|128|8.0|700|30|471|8|0
Whiplash|2014|US|Drama,Music|Damien Chazelle|Miles Teller,J.K. Simmons,Melissa Benoist|Sony Pictures Classics||en|107|8.5|1000|3.3|49|9|0
Babylon|2022|US|Drama,Comedy|Damien Chazelle|Brad Pitt,Margot Robbie,Diego Calva|Paramount Pictures||en|189|7.1|160|80|63|7|0
Everything Everywhere All at Once|2022|US|Action,Adventure,Science Fiction|Daniel Kwan,Daniel Scheinert|Michelle Yeoh,Ke Huy Quan,Stephanie Hsu|A24||en|139|7.8|550|14.3|143|9|0
Get Out|2017|US|Horror,Mystery,Thriller|Jordan Peele|Daniel Kaluuya,Allison Williams,Catherine Keener|Blumhouse Productions||en|104|7.8|700|4.5|255|8|0
Paranormal Activity|2007|US|Horror,Mystery|Oren Peli|Katie Featherston,Micah Sloat|Blumhouse Productions||en|86|6.3|260|0.015|193|9|0
Toy Story|1995|US|Animation,Comedy,Family|John Lasseter|Tom Hanks,Tim Allen,Don Rickles|Pixar|Toy Story Collection|en|81|8.3|1100|30|394|9|0
Toy Story 3|2010|US|Animation,Comedy,Family|Lee Unkrich|Tom Hanks,Tim Allen,Joan Cusack|Pixar|Toy Story Collection|en|103|8.3|900|200|1067|9|0
Up|2009|US|Animation,Comedy,Family,Adventure|Pete Docter|Ed Asner,Christopher Plummer,Jordan Nagai|Pixar||en|96|8.3|1150|175|735|9|0
Coco|2017|US|Animation,Family,Fantasy,Music|Lee Unkrich|Anthony Gonzalez,Gael García Bernal,Benjamin Bratt|Pixar||en|105|8.4|600|175|814|10|0
The Avengers|2012|US|Science Fiction,Action,Adventure|Joss Whedon|Robert Downey Jr.,Chris Evans,Mark Ruffalo,Scarlett Johansson|Marvel Studios|The Avengers Collection|en|143|8.0|1500|220|1519|7|0
Avengers: Endgame|2019|US|Adventure,Science Fiction,Action|Anthony Russo,Joe Russo|Robert Downey Jr.,Chris Evans,Mark Ruffalo,Scarlett Johansson|Marvel Studios|The Avengers Collection|en|181|8.4|1300|356|2799|8|0
Titanic|1997|US|Drama,Romance|James Cameron|Leonardo DiCaprio,Kate Winslet,Billy Zane|Paramount Pictures||en|194|7.9|1300|200|2264|5|0
Gladiator|2000|US|Action,Drama,Adventure|Ridley Scott|Russell Crowe,Joaquin Phoenix,Connie Nielsen|DreamWorks Pictures||en|155|8.5|1700|103|465|9|0
The Shawshank Redemption|1994|US|Drama,Crime|Frank Darabont|Tim Robbins,Morgan Freeman,Bob Gunton|Castle Rock Entertainment||en|142|9.3|3000|25|58|10|1
The Godfather|1972|US|Drama,Crime|Francis Ford Coppola|Marlon Brando,Al Pacino,James Caan|Paramount Pictures|The Godfather Collection|en|175|9.2|2100|6|250|10|1
The Godfather Part II|1974|US|Drama,Crime|Francis Ford Coppola|Al Pacino,Robert De Niro,Robert Duvall|Paramount Pictures|The Godfather Collection|en|202|9.0|1400|13|93|9|0
Fargo|1996|US|Crime,Drama,Thriller|Joel Coen,Ethan Coen|Frances McDormand,William H. Macy,Steve Buscemi|Working Title Films||en|98|8.1|720|7|61|8|0
No Country for Old Men|2007|US|Crime,Drama,Thriller|Joel Coen,Ethan Coen|Josh Brolin,Javier Bardem,Tommy Lee Jones|Miramax||en|122|8.2|1100|25|171|9|0
Perfect Days|2023|JP|Drama|Wim Wenders|Kōji Yakusho,Tokio Emoto|Master Mind||ja|124|7.9|50|||9|0
The Worst Person in the World|2021|NO|Comedy,Drama,Romance|Joachim Trier|Renate Reinsve,Anders Danielsen Lie|Oslo Pictures||no|128|7.7|110|||8|0
Close|2022|BE|Drama|Lukas Dhont|Eden Dambrine,Gustav De Waele|Menuet||fr|104|7.8|40|||8|0
Aftersun|2022|GB|Drama|Charlotte Wells|Paul Mescal,Frankie Corio|BBC Film||en|102|7.6|150|||9|0
Past Lives|2023|US|Drama,Romance|Celine Song|Greta Lee,Teo Yoo,John Magaro|A24||en|105|7.8|120|12|42|8|0
Anatomy of a Fall|2023|FR|Crime,Drama,Mystery|Justine Triet|Sandra Hüller,Swann Arlaud,Milo Machado-Graner|Les Films Pelléas||fr|151|7.7|220|6.2|36|8|0
In the Mood for Love|2000|HK|Drama,Romance|Wong Kar-wai|Tony Leung Chiu-wai,Maggie Cheung|Jet Tone Production||cn|98|8.1|170|||9|0
Crouching Tiger, Hidden Dragon|2000|TW|Adventure,Drama,Action|Ang Lee|Chow Yun-fat,Michelle Yeoh,Zhang Ziyi|Columbia Pictures||zh|120|7.9|280|17|213|7|0
3 Idiots|2009|IN|Drama,Comedy|Rajkumar Hirani|Aamir Khan,Madhavan,Sharman Joshi|Vinod Chopra Films||hi|170|8.4|430|||8|0
RRR|2022|IN|Action,Drama|S. S. Rajamouli|N. T. Rama Rao Jr.,Ram Charan,Alia Bhatt|DVV Entertainment||te|187|7.8|160|72|160|8|0
Leviathan|2014|RU|Drama|Andrey Zvyagintsev|Aleksey Serebryakov,Elena Lyadova|Non-Stop Production||ru|140|7.5|60|||7|0
The Seventh Seal|1957|SE|Drama,Fantasy|Ingmar Bergman|Max von Sydow,Gunnar Björnstrand,Bengt Ekerot|Svensk Filmindustri||sv|96|8.1|200|||8|0
Ida|2013|PL|Drama|Paweł Pawlikowski|Agata Trzebuchowska,Agata Kulesza|Opus Film||pl|82|7.4|60|||8|0
District 9|2009|ZA|Science Fiction,Action,Thriller|Neill Blomkamp|Sharlto Copley,Jason Cope,David James|WingNut Films||en|112|7.9|720|30|211|8|0
No|2012|CL|Drama,History|Pablo Larraín|Gael García Bernal,Alfredo Castro|Fabula||es|118|7.4|30|||8|0
Winter Sleep|2014|TR|Drama|Nuri Bilge Ceylan|Haluk Bilginer,Melisa Sözen|Zeyno Film||tr|196|8.0|55|||8|0
The Banshees of Inisherin|2022|IE|Drama,Comedy|Martin McDonagh|Colin Farrell,Brendan Gleeson,Kerry Condon|Film4||en|114|7.7|250|20|50|9|0
"""
PENDIENTES = """Tokyo Story|1953|JP
Stalker|1979|RU
Burning|2018|KR
Lawrence of Arabia|1962|GB
Persona|1966|SE
Yi Yi|2000|TW
Ran|1985|JP
Petite Maman|2021|FR
The Zone of Interest|2023|GB
Killers of the Flower Moon|2023|US
Central Station|1998|BR
Embrace of the Serpent|2015|CO"""
# vistas hace poco en Dixmax y aún sin registrar en Letterboxd (salen en la revisión)
SIN_LB = {"Anatomy of a Fall", "Perfect Days", "The Banshees of Inisherin", "Past Lives"}
FECHAS_FIJAS = {  # un maratón y una racha para las curiosidades
    "The Lord of the Rings: The Fellowship of the Ring": "2025-12-28", "The Lord of the Rings: The Two Towers": "2025-12-28",
    "The Lord of the Rings: The Return of the King": "2025-12-28",
    "Memento": "2024-08-10", "Batman Begins": "2024-08-11", "The Dark Knight": "2024-08-12", "Inception": "2024-08-13",
    "Interstellar": "2024-08-14", "Oppenheimer": "2024-08-15",
    "Anatomy of a Fall": "2026-11-08", "Perfect Days": "2026-11-11", "The Banshees of Inisherin": "2026-11-13",
    "Past Lives": "2026-11-15",
}

# ---------------- series ----------------
# título|año|país|géneros|cadena|min/ep|episodios por temporada|estado|nota|♥|TVmaze peso|TVmaze nota|reparto|inicio
SERIES = """
Breaking Bad|2008|US|Drama,Crime|AMC|47|7,13,13,13,16|finished|10|1|99|9.2|Bryan Cranston,Aaron Paul,Anna Gunn,Dean Norris,Bob Odenkirk|2023-01-08
Better Call Saul|2015|US|Drama,Crime|AMC|46|10,10,10,10,10,13|finished|9|1|98|8.8|Bob Odenkirk,Rhea Seehorn,Jonathan Banks,Giancarlo Esposito|2023-05-02
The Office|2005|US|Comedy|NBC|22|6,22,25,19,28,26,26,24,25|finished|8|0|99|8.6|Steve Carell,Rainn Wilson,John Krasinski,Jenna Fischer|2023-02-10
Dark|2017|DE|Drama,Mystery,Sci-Fi & Fantasy|Netflix|55|10,8,8|finished|9|1|96|8.6|Louis Hofmann,Oliver Masucci,Jördis Triebel,Lisa Vicari|2024-02-03
La casa de papel|2017|ES|Crime,Drama|Antena 3|50|9,6,8,8,10|finished|7|0|97|8.0|Úrsula Corberó,Álvaro Morte,Itziar Ituño,Pedro Alonso|2023-09-15
Squid Game|2021|KR|Action & Adventure,Mystery,Drama|Netflix|55|9,7|finished|7|0|98|7.9|Lee Jung-jae,Park Hae-soo,Wi Ha-joon,Jung Ho-yeon|2025-01-04
Severance|2022|US|Drama,Mystery,Sci-Fi & Fantasy|Apple TV+|50|9,7|watching|9|1|97|8.4|Adam Scott,Britt Lower,Zach Cherry,John Turturro|2026-01-17
The Bear|2022|US|Comedy,Drama|FX|32|8,10,10,8|watching|8|0|96|8.1|Jeremy Allen White,Ebon Moss-Bachrach,Ayo Edebiri|2026-06-27
Succession|2018|US|Drama|HBO|62|10,10,9,10|finished|9|0|97|8.5|Brian Cox,Jeremy Strong,Sarah Snook,Kieran Culkin|2024-10-05
Chernobyl|2019|GB|Drama|HBO|65|5|finished|10|1|97|9.1|Jared Harris,Stellan Skarsgård,Emily Watson|2023-06-03
Fleabag|2016|GB|Comedy,Drama|BBC Three|27|6,6|finished|9|0|94|8.4|Phoebe Waller-Bridge,Sian Clifford,Olivia Colman,Andrew Scott|2024-04-12
Sherlock|2010|GB|Crime,Drama,Mystery|BBC One|88|3,3,3,3|finished|8|0|98|8.7|Benedict Cumberbatch,Martin Freeman,Una Stubbs|2023-11-03
The Crown|2016|GB|Drama|Netflix|58|10,10,10|dropped|7|0|95|8.1|Claire Foy,Olivia Colman,Matt Smith|2024-11-20
Twin Peaks|1990|US|Drama,Mystery,Crime|ABC|47|8,22|finished|9|0|93|8.6|Kyle MacLachlan,Sheryl Lee,Mädchen Amick|2025-03-01
The Sopranos|1999|US|Drama,Crime|HBO|55|13,13,13,13,13,21|finished|10|1|98|9.0|James Gandolfini,Edie Falco,Michael Imperioli,Lorraine Bracco|2025-04-12
The Wire|2002|US|Drama,Crime|HBO|60|13,12,12,13,10|finished|10|0|97|9.0|Dominic West,Idris Elba,Michael K. Williams,Wendell Pierce|2024-05-04
Narcos|2015|US|Crime,Drama|Netflix|50|10,10,10|finished|8|0|96|8.6|Wagner Moura,Pedro Pascal,Boyd Holbrook|2023-07-14
Lupin|2021|FR|Crime,Drama,Mystery|Netflix|47|5,5,7|finished|7|0|93|7.6|Omar Sy,Ludivine Sagnier,Antoine Gouy|2025-09-06
Shōgun|2024|US|Drama,War & Politics|FX|60|10|finished|9|0|95|8.6|Hiroyuki Sanada,Cosmo Jarvis,Anna Sawai|2025-02-08
The Last of Us|2023|US|Drama,Action & Adventure|HBO|55|9,5|watching|8|0|98|8.7|Pedro Pascal,Bella Ramsey,Gabriel Luna|2026-04-18
Arcane|2021|US|Animation,Sci-Fi & Fantasy,Action & Adventure|Netflix|40|9,9|finished|10|1|97|8.9|Hailee Steinfeld,Ella Purnell,Kevin Alexander|2025-11-09
Ted Lasso|2020|US|Comedy,Drama|Apple TV+|35|10,12,12|finished|8|0|96|8.3|Jason Sudeikis,Hannah Waddingham,Brett Goldstein|2024-07-06
Bluey|2018|AU|Animation,Kids,Comedy|ABC Kids|7|48|watching|9|0|92|9.0|Dave McCormack,Melanie Zanetti|2026-08-01
Mindhunter|2017|US|Crime,Drama|Netflix|50|10,9|finished|8|0|95|8.6|Jonathan Groff,Holt McCallany,Anna Torv|2025-06-14
El Ministerio del Tiempo|2015|ES|Sci-Fi & Fantasy,Drama|La 1|70|8,13|dropped|7|0|82|8.0|Rodolfo Sancho,Aura Garrido,Nacho Fresneda|2024-01-13
Borgen|2010|DK|Drama|DR1|58|10,10|watching|8|0|84|8.2|Sidse Babett Knudsen,Birgitte Hjort Sørensen,Pilou Asbæk|2026-09-05
Kingdom|2019|KR|Drama,Mystery,Action & Adventure|Netflix|50|6,6|finished|8|0|90|8.3|Ju Ji-hoon,Bae Doona,Ryu Seung-ryong|2025-10-04
"""
SERIES_PENDIENTES = """Mr. Robot|2015|US
The Leftovers|2014|US
Patria|2020|ES
Babylon Berlin|2017|DE
Top of the Lake|2013|AU"""

# ---------------- anime ----------------
# título|año|país|géneros (AniList)|estudio|min/ep|episodios vistos|estado|nota|♥|popularidad|media|voces|inicio
ANIME = """
Frieren: Beyond Journey's End|2023|JP|Adventure,Drama,Fantasy|Madhouse|24|28|finished|9|1|700000|90|Atsumi Tanezaki,Kana Ichinose,Chiaki Kobayashi,Nobuhiko Okamoto|2026-02-07
Fullmetal Alchemist: Brotherhood|2009|JP|Action,Adventure,Drama,Fantasy|Bones|24|64|finished|10|1|1100000|90|Romi Park,Rie Kugimiya,Shinichiro Miki,Megumi Takamoto|2023-03-04
Attack on Titan|2013|JP|Action,Drama,Fantasy,Mystery|Wit Studio|24|25|finished|8|0|1200000|85|Yuki Kaji,Yui Ishikawa,Marina Inoue,Hiroshi Kamiya|2023-10-07
Death Note|2006|JP|Mystery,Psychological,Supernatural,Thriller|Madhouse|23|37|finished|9|0|1100000|84|Mamoru Miyano,Kappei Yamaguchi,Shido Nakamura|2024-01-20
Cowboy Bebop|1998|JP|Action,Adventure,Drama,Sci-Fi|Sunrise|24|26|finished|10|1|500000|86|Koichi Yamadera,Megumi Hayashibara,Unsho Ishizuka|2024-06-01
Neon Genesis Evangelion|1995|JP|Action,Drama,Mecha,Psychological,Sci-Fi|Gainax|24|26|finished|8|0|450000|83|Megumi Ogata,Megumi Hayashibara,Yuko Miyamura,Kotono Mitsuishi|2024-09-07
Steins;Gate|2011|JP|Drama,Psychological,Sci-Fi,Thriller|White Fox|24|24|finished|9|1|700000|89|Mamoru Miyano,Kana Hanazawa,Asami Imai|2025-01-18
Spy x Family|2022|JP|Action,Comedy,Slice of Life|Wit Studio|24|37|watching|8|0|600000|84|Takuya Eguchi,Atsumi Tanezaki,Saori Hayami|2026-05-02
Jujutsu Kaisen|2020|JP|Action,Drama,Supernatural|MAPPA|24|47|watching|8|0|900000|85|Junya Enoki,Yuichi Nakamura,Yuma Uchida,Asami Seto|2026-03-14
Haikyu!!|2014|JP|Comedy,Drama,Sports|Production I.G|24|25|finished|8|0|500000|82|Ayumu Murase,Kaito Ishikawa,Satoshi Hino|2025-05-03
Mob Psycho 100|2016|JP|Action,Comedy,Slice of Life,Supernatural|Bones|24|37|finished|9|0|500000|85|Setsuo Ito,Takahiro Sakurai,Akio Otsuka|2025-08-02
One Piece|1999|JP|Action,Adventure,Comedy,Fantasy|Toei Animation|24|220|watching|9|1|600000|88|Mayumi Tanaka,Kazuya Nakai,Akemi Okamura,Hiroaki Hirata|2026-06-20
Vinland Saga|2019|JP|Action,Adventure,Drama|Wit Studio|24|24|finished|9|0|400000|88|Yuto Uemura,Naoya Uchida,Akio Otsuka|2025-12-06
Odd Taxi|2021|JP|Drama,Mystery,Psychological|OLM|23|13|finished|9|0|90000|85|Natsuki Hanae,Riho Iida,Ryohei Kimura|2024-03-02
Link Click|2021|CN|Drama,Mystery,Supernatural|LAN Studio|24|11|finished|8|0|80000|84||2025-07-05
Mushishi|2005|JP|Adventure,Mystery,Slice of Life,Supernatural|Artland|24|14|dropped|8|0|120000|86|Yuto Nakano|2024-12-07
"""
ANIME_PENDIENTES = """Monster|2004|JP
Ping Pong the Animation|2014|JP
Chainsaw Man|2022|JP"""


def _filas(txt):
    return [x.split("|") for x in txt.strip().splitlines()]


def _lista(s):
    return [x for x in s.split(",") if x]


def _num(s, factor=1):
    return float(s) * factor if s else None


def _utc(d):
    return d.replace(tzinfo=TZ).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _sesiones(rng, inicio, n_eps, rt, ritmo=(1, 2, 2, 3), hueco=(1, 2, 3, 4, 6), maraton=False):
    """Fechas (hora de Madrid) de n_eps episodios: sesiones de 1-3 por la noche, con días de descanso."""
    out, dia = [], datetime.combine(inicio, datetime.min.time())
    while len(out) < n_eps:
        finde = dia.weekday() >= 5
        n = rng.choice((4, 6, 8, 12) if maraton and finde else (2, 3, 4, 5) if maraton else ritmo)
        h = rng.choice((16, 17, 18, 21, 22) if finde else (20, 21, 21, 22, 22, 23, 23, 0))
        t = dia + timedelta(hours=h + (24 if h == 0 else 0), minutes=rng.randrange(0, 50))
        for _ in range(min(n, n_eps - len(out))):
            t += timedelta(minutes=rt + rng.randrange(2, 9))
            out.append(t)
        dia += timedelta(days=1 if maraton else rng.choice(hueco))
    return out


def _datos():
    rng = random.Random(7)
    base = {"pelis": [], "series": [], "lb": [], "al": {}, "anime": {}, "sz": {"sz_diario": 0}, "fecha": REVISION,
            "sin_dixmax": False}
    meta = {k: {} for k in ("pelis", "paises", "dinero", "series", "anime", "tvmaze")}
    # películas: fechas repartidas entre 2023 y hoy (como mucho 2 el mismo día), salvo las fijas
    usados = {}
    dias = (HOY - date(2023, 1, 5)).days
    for i, f in enumerate(_filas(PELIS)):
        t, y, pais, g, dire, cast, st, col, lang, rt, ir, inn, cost, taq, r, fav = f
        tmdb, fid = 9000 + i, 100 + i
        d = FECHAS_FIJAS.get(t)
        while not d:
            x = (date(2023, 1, 5) + timedelta(days=rng.randrange(dias - 20))).isoformat()
            if usados.get(x, 0) < 2 and not any(x == v for v in FECHAS_FIJAS.values()):
                d = x
        usados[d] = usados.get(d, 0) + 1
        hora = rng.choice((17, 21, 22, 22, 23))
        base["pelis"].append({"id": fid, "tmdb": tmdb, "t": t, "y": y, "st": "watched", "d": f"{d}T{hora}:30:00",
                              "r": float(r), "fav": fav == "1"})
        if t not in SIN_LB:
            base["lb"].append({"t": t, "y": y, "w": True, "r": float(r) / 2, "like": fav == "1",
                               "diario": [[d, False]] + ([["2026-02-14", True]] if t == "The Matrix" else [])})
        meta["pelis"][str(tmdb)] = {"v": 2, "imdb_n": int(float(inn) * 1000), "imdb_r": float(ir), "tmdb_n": 0, "pop": None,
                                    "rt": int(rt), "g": _lista(g), "st": st or None, "col": col or None, "lang": lang,
                                    "dir": _lista(dire), "cast": _lista(cast)}
        meta["paises"][str(tmdb)] = [pais]
        meta["dinero"][str(tmdb)] = [_num(cost, 1e6), _num(taq, 1e6), True]
    for i, (t, y, pais) in enumerate(_filas(PENDIENTES)):
        tmdb = 9500 + i
        base["pelis"].append({"id": 600 + i, "tmdb": tmdb, "t": t, "y": y, "st": "watchlist", "d": None, "r": None, "fav": False})
        meta["paises"][str(tmdb)] = [pais]

    def serie(i, t, y, st, r, fav, fechas, eps_temp):
        eps, k = [], 0
        for se, n in enumerate(eps_temp, 1):
            for ep in range(1, n + 1):
                if k < len(fechas):
                    eps.append([se, ep, _utc(fechas[k]), False])
                    k += 1
        return {"id": 2000 + i, "tmdb": 7000 + i, "t": t, "y": y, "st": st, "r": float(r) if r else None,
                "fav": fav == "1", "eps": eps}
    for i, f in enumerate(_filas(SERIES)):
        t, y, pais, g, red, rt, temps, st, r, fav, w, tr, cast, ini = f
        temps = [int(x) for x in temps.split(",")]
        fechas = _sesiones(rng, date.fromisoformat(ini), sum(temps), int(rt),
                           ritmo=(2, 3, 4, 5) if int(rt) < 15 else (1, 2, 2, 3), maraton=t == "Chernobyl")
        s = serie(i, t, y, st, r, fav, fechas, temps)
        base["series"].append(s)
        meta["series"][str(s["tmdb"])] = {"pais": [pais], "g": _lista(g), "red": [red], "rt": int(rt), "eps": sum(temps)}
        meta["tvmaze"][str(s["tmdb"])] = {"v": 3, "w": int(w), "r": float(tr), "cast": _lista(cast), "inv": {}}
    for j, (t, y, pais) in enumerate(_filas(SERIES_PENDIENTES), 100):
        base["series"].append({"id": 2000 + j, "tmdb": 7000 + j, "t": t, "y": y, "st": "watchlist", "r": None, "fav": False, "eps": []})
        meta["series"][str(7000 + j)] = {"pais": [pais], "g": ["Drama"], "red": [], "rt": 50, "eps": 10}
    for i, f in enumerate(_filas(ANIME)):
        t, y, pais, g, estudio, rt, n, st, r, fav, pop, media, voces, ini = f
        n = int(n)
        if t == "One Piece":  # un verano de maratones
            fechas = _sesiones(rng, date.fromisoformat(ini), n, int(rt), maraton=True)
        else:
            fechas = _sesiones(rng, date.fromisoformat(ini), n, int(rt), ritmo=(2, 3, 3, 4), hueco=(1, 1, 2, 3))
        s = serie(300 + i, t, y, st, r, fav, fechas, [n])
        base["series"].append(s)
        al = 150000 + i
        base["anime"][str(s["id"])] = al
        base["al"][str(al)] = {"st": {"finished": "COMPLETED", "watching": "CURRENT", "dropped": "DROPPED"}[st],
                               "p": n, "r": float(r)}
        meta["anime"][str(al)] = {"v": 4, "g": _lista(g), "pais": pais, "rt": int(rt), "pop": int(pop), "media": int(media),
                                  "st": [estudio], "voces": _lista(voces)}
    for j, (t, y, pais) in enumerate(_filas(ANIME_PENDIENTES), 400):
        s = {"id": 2000 + j, "tmdb": 7000 + j, "t": t, "y": y, "st": "watchlist", "r": None, "fav": False, "eps": []}
        base["series"].append(s)
        al = 160000 + j
        base["anime"][str(s["id"])] = al
        meta["anime"][str(al)] = {"v": 4, "g": ["Drama"], "pais": pais, "rt": 24, "pop": 100000, "media": 85, "st": [], "voces": []}
    # fuera lo que caería después de HOY (las series en curso se quedan a medias)
    for s in base["series"]:
        s["eps"] = [e for e in s["eps"] if e[2][:10] <= HOY.isoformat()]
    base["sz"]["sz_diario"] = sum(len(s["eps"]) for s in base["series"]) + 40
    return base, meta


# ---------------- revisión, historial ----------------
IGN = {"clave": "ignorar", "texto": "Ignorar", "fase": 1}


def _diferencias(base):
    pel = {m["t"]: m for m in base["pelis"]}
    ser = {s["t"]: s for s in base["series"]}
    out = []

    def peli(cat, t, detalle, opciones, lb=None):
        m = pel[t]
        dx = {"id": m["id"], "tmdb": m["tmdb"], "title": t, "year": m["y"], "status": m["st"], "date": m["d"],
              "rating10": m["r"], "favorite": m["fav"], "url": f"https://playmax.mx/x-f{m['id']}"}
        out.append({"id": f"p{len(out)}", "seccion": "Películas", "categoria": cat,
                    "titulo": f"{t} ({m['y']}) = {t} ({m['y']})", "detalle": detalle,
                    "enlaces": {"Dixmax": dx["url"], "Letterboxd": f"https://letterboxd.com/tmdb/{m['tmdb']}/"},
                    "opciones": opciones + [IGN], "datos": {"dx": dx, "lb": lb or {"name": t, "year": m["y"]}}})
    log_lb = {"clave": "lb_log", "texto": "Registrar en Letterboxd (diario con fecha y nota de Dixmax)", "fase": 3}
    wl_lb = {"clave": "lb_watchlist", "texto": "Añadir a la watchlist de Letterboxd", "fase": 3}
    for t in ("Anatomy of a Fall", "Perfect Days", "The Banshees of Inisherin", "Past Lives"):
        peli("Vista en Dixmax, no en Letterboxd", t, f"Vista el {pel[t]['d'][:10]}", [log_lb])
    notas = [{"clave": "nota_dx_a_lb", "texto": "Poner la nota de Dixmax en Letterboxd", "fase": 3},
             {"clave": "nota_lb_a_dx", "texto": "Poner la nota de Letterboxd en Dixmax", "fase": 2}]
    for t, lb in (("La La Land", 3.5), ("Gladiator", 4.0), ("Arrival", 4.0)):
        r = pel[t]["r"]
        peli("Nota distinta", t, f"Dixmax {r:g} ({r / 2}★) · Letterboxd {lb}★", notas)
    for t in ("Tokyo Story", "Stalker", "Burning"):
        peli("Pendiente en Dixmax, no en watchlist de Letterboxd", t, "", [wl_lb])
    peli("Me gusta en Letterboxd, no favorita en Dixmax", "Coco", "En Dixmax «Favorita» sustituye a «Vista» (sigue en tu lista de vistas)",
         [{"clave": "dx_favorita", "texto": "Marcar como favorita en Dixmax", "fase": 2}])

    def show(cat, t, detalle, opciones, datos=None):
        s = ser[t]
        out.append({"id": f"s{len(out)}", "seccion": "Series", "categoria": cat, "titulo": t, "detalle": detalle,
                    "enlaces": {"Dixmax": f"https://playmax.mx/x-f{s['id']}", "Serializd": f"https://www.serializd.com/show/{s['tmdb']}"},
                    "opciones": opciones + [IGN], "datos": {"tmdb": s["tmdb"], **(datos or {}),
                                                            "show": {"id": s["id"], "tmdb": s["tmdb"], "title": t}}})
    subir = [{"clave": "sz_subir_eps", "texto": "Subir a Serializd con fecha de Dixmax", "fase": 2}]
    for t in ("Severance", "The Bear", "Bluey"):
        ult = ser[t]["eps"][-3:]
        show("Episodios sin subir a Serializd", t, f"{len(ult)} episodios (p. ej. " + ", ".join("S%02dE%02d" % (e[0], e[1]) for e in ult) + ")", subir)
    show("Estado distinto", "The Last of Us", "Dixmax: viendo · Serializd: pendiente",
         [{"clave": "sz_estado", "texto": "Dejarla solo como 'viendo' en Serializd", "fase": 2}])
    show("Estado distinto", "The Crown", "Dixmax: abandonada · Serializd: viendo",
         [{"clave": "sz_estado", "texto": "Dejarla solo como 'abandonada' en Serializd", "fase": 2}])
    show("Nota de serie sin subir a Serializd", "Shōgun", "Dixmax 9.0 → 9",
         [{"clave": "sz_nota", "texto": "Subir la nota a Serializd", "fase": 2}])
    show("Terminada en Dixmax sin registro de serie en Serializd", "Chernobyl", "",
         [{"clave": "sz_terminar", "texto": "Marcar terminada en Serializd (temporadas + registro + nota)", "fase": 2}])

    def anime(cat, t, detalle):
        s = ser[t]
        al = base["anime"][str(s["id"])]
        out.append({"id": f"a{len(out)}", "seccion": "Anime", "categoria": cat, "titulo": t, "detalle": detalle,
                    "enlaces": {"Dixmax": f"https://playmax.mx/x-f{s['id']}", "AniList": f"https://anilist.co/anime/{al}"},
                    "opciones": [{"clave": "al_subir", "texto": "Subir a AniList (estado, episodios, nota y fechas)", "fase": 2}, IGN],
                    "datos": {"entradas": [{"mediaId": al}]}})
    anime("Distinto en AniList", "Frieren: Beyond Journey's End",
          "Frieren: Beyond Journey's End: viendo → completado, episodios 24 → 28, nota 8.5 → 9, fecha de fin")
    anime("Distinto en AniList", "One Piece", "One Piece: episodios 212 → 220")
    anime("Falta en AniList", "Odd Taxi", "Odd Taxi: añadir como completado (13 ep.)")
    return out


def _stats(base, atras=0):
    """Cifras de la revisión de hace «atras» revisiones (cada una con un poco menos visto)."""
    pe, ep, lb, al = ([0, 1, 1, 2, 3][atras], [0, 11, 14, 20, 22][atras], [0, 1, 1, 2, 2][atras], [0, 0, 0, 1, 1][atras])
    p = [m for m in base["pelis"]]
    s = [x for x in base["series"]]
    return {"dx_pelis_vistas": sum(m["st"] == "watched" for m in p) - pe, "dx_pelis_pendientes": sum(m["st"] == "watchlist" for m in p),
            "dx_pelis_favoritas": sum(m["fav"] for m in p), "dx_series_terminadas": sum(x["st"] == "finished" for x in s),
            "dx_series_siguiendo": sum(x["st"] == "watching" for x in s), "dx_series_pendientes": sum(x["st"] == "watchlist" for x in s),
            "dx_series_favoritas": sum(x["fav"] for x in s), "dx_episodios": sum(len(x["eps"]) for x in s) - ep,
            "lb_vistas": len(base["lb"]) - lb, "lb_watchlist": 9, "lb_me_gusta": sum(f["like"] for f in base["lb"]) + 1,
            "lb_diario": sum(len(f["diario"]) for f in base["lb"]) - lb, "sz_diario": base["sz"]["sz_diario"] - ep,
            "sz_vistas": 22, "sz_favoritas": 8, "al_anime": 17 - al, "al_favoritos": 5}


def _historial(base, difs):
    from collections import Counter
    fuentes = {"dixmax": "API en directo", "letterboxd": "letterboxd-demo-2026-11-16-utc", "serializd": "demo", "anilist": "Demo"}
    novs = [["🎬 Past Lives: añadida como vista, nota 8", "📺 Severance: +2 episodios (T2E6–T2E7)", "📺 One Piece: +9 episodios (T1E212–T1E220)"],
            ["🎬 The Banshees of Inisherin: añadida como vista, nota 9", "📺 The Bear: +3 episodios (T4E6–T4E8)"],
            ["🎬 Perfect Days: añadida como vista, nota 9", "📺 Bluey: +6 episodios (T1E40–T1E45)", "📺 Arcane: ♥ favorita"],
            ["🎬 Anatomy of a Fall: añadida como vista, nota 8", "📺 Borgen: +2 episodios (T2E3–T2E4)"],
            []]
    fechas = ["16/11/2026 21:04", "14/11/2026 22:41", "12/11/2026 20:15", "09/11/2026 23:02", "05/11/2026 19:37"]
    hist = []
    for i in range(len(fechas) - 1, -1, -1):
        d = difs if i == 0 else difs[: max(4, len(difs) - 3 * i)]
        hist.append({"fecha": fechas[i], "modo": "rápida" if i % 2 == 0 else "completa", "segundos": 9 if i % 2 == 0 else 54,
                     "diferencias": len(d), "categorias": dict(Counter(x["categoria"] for x in d)), "fuentes": fuentes,
                     "stats": _stats(base, i), "novedades": novs[i],
                     "detalle": [{"c": x["categoria"], "t": x["titulo"], "d": x["detalle"][:160]} for x in d]})
        if i == 2:
            hist.append({"fecha": "12/11/2026 20:19", "modo": "aplicación", "segundos": None, "aplicadas": 3, "total": 3,
                         "acciones": [{"c": "Episodios sin subir a Serializd", "t": "Arcane", "a": "Subir a Serializd con fecha de Dixmax", "ok": True},
                                      {"c": "Distinto en AniList", "t": "Vinland Saga", "a": "Subir a AniList (estado, episodios, nota y fechas)", "ok": True},
                                      {"c": "Nota distinta", "t": "Dune: Part Two (2024) = Dune: Part Two (2024)", "a": "Poner la nota de Dixmax en Letterboxd", "ok": True}]})
    return hist


def _escribir(p, datos):
    p.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def generar(dest):
    """Escribe la demo en dest (carpeta nueva o vacía) y calcula sus estadísticas sin red."""
    dest = Path(dest).resolve()
    if dest.exists() and any(dest.iterdir()) and not (dest / ".demo-trisync").exists():
        raise SystemExit(f"{dest} no está vacía: usa una carpeta nueva")
    cache = dest / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (dest / ".demo-trisync").write_text("demo\n", encoding="utf-8")
    base, meta = _datos()
    # export de Letterboxd de mentira (solo para que la tarjeta de Letterboxd tenga fecha)
    ex = dest / "exports" / "letterboxd-demo-2026-11-16-utc"
    ex.mkdir(parents=True, exist_ok=True)
    for n, cab, filas in (("watched.csv", ["Date", "Name", "Year", "Letterboxd URI"], [[f["diario"][0][0], f["t"], f["y"], ""] for f in base["lb"]]),
                          ("ratings.csv", ["Date", "Name", "Year", "Letterboxd URI", "Rating"], [[f["diario"][0][0], f["t"], f["y"], "", f["r"]] for f in base["lb"]]),
                          ("diary.csv", ["Date", "Name", "Year", "Letterboxd URI", "Rating", "Rewatch", "Tags", "Watched Date"],
                           [[d, f["t"], f["y"], "", f["r"], "Yes" if rw else "", "", d] for f in base["lb"] for d, rw in f["diario"]]),
                          ("watchlist.csv", ["Date", "Name", "Year", "Letterboxd URI"], [])):
        with open(ex / n, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cab)
            w.writerows(filas)
    hace = time.time() - 3 * 3600
    os.utime(ex, (hace, hace))
    (dest / ".env").write_text("\n".join([
        f"DATA_DIR={dest / 'exports'}", "SERIALIZD_USER=demo", "LETTERBOXD_USER=demo", "SERIALIZD_TOKEN=demo",
        "DIXMAX_API_KEY=demo", "DIXMAX_AUTH_KEY=demo", "ANILIST_USER=Demo", "ANILIST_TOKEN=demo",
        "ANILIST_EXPIRA=16/11/2027", "IDIOMA=es"]) + "\n", encoding="utf-8")
    for nombre, clave in (("meta_pelis.json", "pelis"), ("meta_paises.json", "paises"), ("meta_dinero4.json", "dinero"),
                          ("meta_series.json", "series"), ("meta_anime.json", "anime"), ("meta_tvmaze.json", "tvmaze")):
        _escribir(cache / nombre, meta[clave])
    _escribir(cache / "base_stats.json", base)
    difs = _diferencias(base)
    _escribir(cache / "diff.json", {"fuentes": {"dixmax": "API en directo", "letterboxd": "letterboxd-demo-2026-11-16-utc",
                                                "serializd": "demo", "anilist": "Demo"},
                                    "diferencias": difs, "modo": "rápida", "calculado": REVISION, "stats": _stats(base)})
    _escribir(cache / "historial.json", _historial(base, difs))
    # estadísticas con el código de la app, en otro proceso (core.config lee TRISYNC_DATOS al importarse)
    env = {**os.environ, "TRISYNC_DATOS": str(dest), "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, "-c", "from tools.demo import _calcular; _calcular()"], cwd=ROOT, env=env, check=True)
    return dest


def _calcular():
    """Dentro del proceso con TRISYNC_DATOS = la demo: sin red (todo sale de las fichas escritas arriba)."""
    import urllib.request

    from core import config, estadisticas, http, metadatos

    def sin_red(*a, **k):
        raise RuntimeError("demo: sin red")
    urllib.request.urlopen = http.call = metadatos.call = sin_red
    config.dixmax_api = lambda: False  # sin fichas de Dixmax: país, géneros y reparto salen de las fichas de arriba
    if not (config.DATOS / ".demo-trisync").exists():
        raise SystemExit("TRISYNC_DATOS no apunta a la demo")
    estadisticas.calcular(progress=lambda m: None)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(f"Demo en {generar(sys.argv[1])}")
