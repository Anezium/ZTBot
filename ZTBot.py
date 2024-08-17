import requests
from time import sleep
import discord
from discord.ext import commands
from discord.ui import Button, View
from datetime import datetime
from bs4 import BeautifulSoup
import re

# Création de l'instance du bot
bot = commands.Bot(command_prefix='/', intents=discord.Intents.all())



class ZoneTelechargementParser:
    def __init__(self, dev_mode=False):
        self._ZTBaseURL = None
        self._allCategories = ["films", "series", "jeux", "musiques", "mangas", "ebooks", "autres-videos", "logiciels", "mobiles"]
        self._lastAxiosRequestTimestamp = 0
        self._dev_mode = dev_mode
        self._request_delay = 300  # Hardcoded delay between requests in milliseconds

    def _get_base_url(self):
        return self._ZTBaseURL

    def update_url_from_api(self):
        api_url = "https://matthieuev.github.io/Zt-url-api/url.json"
        
        response = requests.get(api_url)
        
        if response.status_code == 200:
            data = response.json()
            self._ZTBaseURL = data.get("url", "")
        else:
            print(f"Erreur lors de la récupération de l'URL : {response.status_code}")

    def _get_all_categories(self):
        return self._allCategories

    def _get_matching_groups(self, s):
        try:
            return re.findall(r'\((.*?)\)', s)
        except Exception as e:
            if self._dev_mode:
                print(e)
            return s

    def _get_payload_url_from_query(self, category, query, page=1):
        if not isinstance(page, int):
            raise ValueError("Page must be of type 'int'.")
        category = category.strip().lower() 
        if category not in self._allCategories:
            raise ValueError(f"Category must be one in the following list: {', '.join(self._get_all_categories())}")
        return f"{self._get_base_url()}/?p={category}&search={requests.utils.quote(query)}&page={page}"

    def _get_dom_element_from_url(self, url):
        # Simple delay between requests
        current_time = datetime.now().timestamp() * 1000
        if current_time - self._lastAxiosRequestTimestamp < self._request_delay:
            sleep((self._request_delay - (current_time - self._lastAxiosRequestTimestamp)) / 1000)
        self._lastAxiosRequestTimestamp = datetime.now().timestamp() * 1000

        response = requests.get(url)
        document = BeautifulSoup(response.content, 'html.parser')
        return document

    def _parse_movies_from_search_query(self, category, query, page):
        payload_url = self._get_payload_url_from_query(category, query, page)
        document = self._get_dom_element_from_url(payload_url)

        movie_list_elements = [x for x in document.select('#dle-content .cover_global')]
        response_movie_list = []

        if len(movie_list_elements) == 0:
            return response_movie_list

        for elem in movie_list_elements:
            the_url = self._get_base_url() + elem.select('.cover_infos_title a')[0]['href']

            detail_release = [
                b.get_text() for x in elem.select('.cover_infos_global')
                for b in x.find_all('b')
            ]

            publish_date = datetime.strptime(elem.select('time')[0].get_text(), '%d %B %Y')

            movie_datas = {
                "title": elem.select('.cover_infos_title a')[0].get_text(),
                "url": the_url,
                "id": re.search(r'\d+', re.search(r'[?&]id=\d+-', the_url).group()).group(),
                "image": self._get_base_url() + elem.select('img')[0]['src'],
                "quality": detail_release[0],
                "language": detail_release[1][1:-1],
                "publishedOn": publish_date,
                "publishedTimestamp": publish_date.timestamp(),
            }
            response_movie_list.append(movie_datas)

        return response_movie_list

    def use_base_url(self, url):
        self._ZTBaseURL = url
        return True

    def search_all(self, category, query):
        try:
            response_movie_list = []
            temp_movie_list = []
            search_page = 0
            while temp_movie_list is not None and len(temp_movie_list) > 0:
                search_page += 1
                temp_movie_list = self._parse_movies_from_search_query(category, query, search_page)
                response_movie_list.extend(temp_movie_list)
                print(f"Added {len(temp_movie_list)} movies from page {search_page}")
            return response_movie_list
        except Exception as e:
            if self._dev_mode:
                print(e)
            return {
                "status": False,
                "error": str(e),
                "stack": str(e).split("\n"),
            }
    
    def get_download_links(self, movie_id):
        movie_url = f"{self._get_base_url()}?p=film&id={movie_id}"
        document = self._get_dom_element_from_url(movie_url)

        download_links = {}

        # Le div qui contient les liens de téléchargement
        download_section = document.find("div", {"id": re.compile(r"news-id-\d+")})

        if download_section:
            # Trouver toutes les balises <div> qui contiennent le nom de l'hôte
            hosts = download_section.find_all("div", style=re.compile(r"font-weight:bold;color:.*"))
            
            for host in hosts:
                host_name = host.get_text(strip=True)
                link = host.find_next("a", href=True)
                if link:
                    download_links[host_name] = link["href"]
                else:
                    print(f"No link found for host {host_name}")  # Debugging line

        return download_links


    def search(self, category, query, page):
        try:
            return self._parse_movies_from_search_query(category, query, page)
        except Exception as e:
            if self._dev_mode:
                print(e)
            return {
                "status": False,
                "error": str(e),
                "stack": str(e).split("\n"),
            }

    def get_movie_details(self, movie_id):
        movie_url = f"{self._get_base_url()}?p=film&id={movie_id}"
        if not movie_url.startswith(self._get_base_url()):
            return {"status": False, "error": "Wrong base URL provided"}

        if self._dev_mode:
            print("movieURL:", movie_url)

        document = self._get_dom_element_from_url(movie_url)

        corps_element = (
            document.select_one("#dle-content .base .maincont .corps")
        )
        main_element = corps_element.select_one('div')

        otherversions_div = main_element.select_one(".otherversions")
        version_list_a = otherversions_div.find_all('a')
        versions = [
            {
                "url": self._get_base_url() + x['href'],
                "quality": x.find_all('b')[0].get_text(),
                "language": self._get_matching_groups(x.find_all('b')[1].get_text())[0],
            }
            for x in version_list_a
        ]

        movie_infos = {
            "name": main_element.select_one('strong').get_text().strip(),
            "synopsis": main_element.select_one('em').get_text().strip(),
        }

        return {
            "movieInfos": movie_infos,
            "otherVersions": versions,
        }

# Variables globales
search_results = []
items_per_page = 5
current_page = 0

# Fonction pour générer le contenu d'une page
def generate_page_content(page):
    start = page * items_per_page
    end = start + items_per_page
    page_content = ""

    for i, item in enumerate(search_results[start:end], start=1):
        title = item.get('title')
        quality = item.get('quality')
        size = item.get('size', 'N/A')  # Remplacer 'size' par les attributs corrects de votre parser

        page_content += f"**{i}. {title}**"
        page_content += f"Qualité: {quality} \n\n"

    return page_content

# Fonction pour générer les boutons de choix
def generate_emotes(search_results, page):
    emotes = []
    start = page * items_per_page
    end = start + items_per_page
    zt_parser = ZoneTelechargementParser(dev_mode=True)  # Créez l'instance ici

    for i, item in enumerate(search_results[start:end], start=1):
        movie_id = item.get('id')
        emote = Button(label=f"Select {i}", style=discord.ButtonStyle.success)
        
        async def callback(interaction: discord.Interaction, movie_id=movie_id):
            links = zt_parser.get_download_links(movie_id)
            if links:
                links_message = "\n".join([f"{host}: {link}" for host, link in links.items()])
            else:
                links_message = "Aucun lien de téléchargement trouvé."
            
            # Envoyer les liens de téléchargement dans un nouveau message
            await interaction.response.send_message(f"Liens pour {item['title']}:\n{links_message}", ephemeral=True)
            
        emote.callback = callback
        emotes.append(emote)
    return emotes


@bot.hybrid_command(name='ztsearch', description='Cherche un film sur ZT.')
async def ztsearch(ctx: commands.Context, film: str):
    global current_page, search_results

    current_page = 0
    zt_parser = ZoneTelechargementParser(dev_mode=True)
    zt_parser.update_url_from_api()
    category = "films"
    page = 1
    
    search_results = zt_parser.search(category, film, page)
    if not search_results:
        await ctx.send("Aucun résultat trouvé.")
        return

    # Génération du contenu de la première page
    page_content = generate_page_content(current_page)

    # Vérification de la longueur du contenu pour éviter de dépasser la limite
    if len(page_content) > 4096:
        page_content_parts = [page_content[i:i+4096] for i in range(0, len(page_content), 4096)]
    else:
        page_content_parts = [page_content]

    # Génération des boutons avec les liens de téléchargement
    emotes = generate_emotes(search_results, current_page)

    # Envoi du premier embed avec les boutons
    view = View()
    for emote in emotes:
        view.add_item(emote)
    
    message = await ctx.send(embed=discord.Embed(
        title=f"Résultats pour '{film}' (Page {current_page + 1})",
        description=page_content_parts[0]
    ), view=view)

    # Ajout des réactions pour la navigation entre les pages
    await message.add_reaction("⬅️")
    await message.add_reaction("➡️")

# Gestionnaire d'événements pour les réactions
@bot.event
async def on_reaction_add(reaction, user):
    global current_page

    # Ignorer les réactions du bot lui-même
    if user == bot.user:
        return

    # Seules les réactions sur les messages du bot sont prises en compte
    if reaction.message.author != bot.user:
        return

    # Gérer les réactions pour changer de page
    if reaction.emoji == "⬅️":
        if current_page > 0:
            current_page -= 1
    elif reaction.emoji == "➡️":
        max_pages = (len(search_results) + items_per_page - 1) // items_per_page  # Calcul du nombre de pages
        if current_page + 1 < max_pages:
            current_page += 1

    # Génération du nouveau contenu de la page
    page_content = generate_page_content(current_page)
    emotes = generate_emotes(search_results, current_page)

    # Vérification de la longueur du contenu pour éviter de dépasser la limite
    if len(page_content) > 4096:
        page_content_parts = [page_content[i:i+4096] for i in range(0, len(page_content), 4096)]
    else:
        page_content_parts = [page_content]

    # Édition du message avec le nouveau contenu de la page
    view = View()
    for emote in emotes:
        view.add_item(emote)
    await reaction.message.edit(embed=discord.Embed(
        title=f"Résultats pour '{reaction.message.embeds[0].title}' (Page {current_page + 1})",
        description=page_content_parts[0]
    ), view=view)

    # Supprimer la réaction de l'utilisateur pour une meilleure UX
    await reaction.remove(user)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.tree.sync()

bot.run("")