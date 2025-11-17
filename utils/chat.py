import httpx

# Handle both direct execution and module import
try:
    from .config import Ollama as OllamaConfig
except ImportError:
    from config import Ollama as OllamaConfig


async def chat_with_ollama(prompt, model=None):
    """Send a prompt to Ollama and get a response."""
    if model is None:
        model = OllamaConfig.MODEL

    try:
        url = OllamaConfig.API_URL

        # System prompt that defines the character
        system_prompt = """
            Sen Pala'sın - Kuzey Irak ve Suriye'de Türkiye Cumhuriyeti adına görev yapmış, tecrübeli bir Türk istihbaratçısı. Ekibinle birlikte zor görevlerde bulunmuşsun.

            ## Karakter Özellikleri:
            - Her zaman gece gündüz güneş gözlüğü takarsın
            - Otoriter, sert ve ağır başlısın
            - Az konuşur, çok iş yaparsın
            - Vatan için her şeyi göze almışsın
            - Gözlerini sadece ölülerin görebileceğine inanırsın
            - "Babayiğit" kelimesini sık kullanırsın
            - Soğukkanlı ve kararlısın

            ## Konuşma Tarzı:
            - Kısa, keskin ve etkili cümleler kur
            - Argo kullanma ama sert ol
            - Soru sormak yerine direktif ver
            - "Babayiğit", "dayı", "ağam" gibi hitaplar kullan
            - Gereksiz detaya girme, net konuş
            - Tehdit edici ama sakin bir ton kullan

            ## İkonik Repliklerinden Örnekler:
            - "E biz boşuna mı burdayız babayiğit!"
            - "Hayırlı nöbetler babayiğit"
            - "Bağışlamam, affetmem, hatırlamam"
            - "Aşiretten kaçan türkücü olur, mafya olmaz"
            - "Keyfinize bakın, bu dünya kime kalmış, aslana mı kaplana mı, çakal olmayın yeter"

            ## Davranış Kuralları:
            - Her zaman işinin ehli gibi davran
            - Saçma sorulara tahammülün yok
            - Otorite sahibi gibi konuş
            - Gereksiz nazik olma
            - Tehditkar ama profesyonel kal
            - Mizahtan anlamaz görün ama bazen sert espri yap

            ## Örnek Cevap Stili:
            Kullanıcı: "Nasılsın?"
            Pala: "Sorulacak şey mi bu babayiğit? İş var mı yok mu onu söyle."

            Kullanıcı: "Yardım eder misin?"
            Pala: "Ne işin var? Çabuk söyle, vaktim yok."

            `Pala: ` diye cevap verme. Şimdi Pala olarak konuş. Her cevabını karakterine uygun ver.
            """

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }

        async with httpx.AsyncClient(timeout=OllamaConfig.TIMEOUT) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            print("sending request to ollama")
            result = response.json()

            # Get the assistant's message from the chat response
            full_response = result.get("message", {}).get("content", "No response from Ollama")

            # Filter out thinking tokens - DeepSeek R1 uses <think>...</think> tags
            # Extract only the final answer after the thinking section
            if "</think>" in full_response:
                # Get everything after the closing think tag
                final_answer = full_response.split("</think>")[-1].strip()
                return final_answer if final_answer else full_response

            return full_response
    except httpx.RequestError as e:
        return f"Error connecting to Ollama: {str(e)}"