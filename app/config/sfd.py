"""Superfighters Deluxe configuration."""

############################# SFD Timezones ############################
TIMEZONES = {
    "New_York": "America/New_York",
    "London": "Europe/London",
    "Tokyo": "Asia/Tokyo",
    "Shanghai": "Asia/Shanghai",
    "Slovakia": "Europe/Bratislava",
    "Russia": "Europe/Moscow",
    "Spain": "Europe/Madrid",
    "Italy": "Europe/Rome",
}
SFD_TIMEZONE_CHOICE = list(TIMEZONES.keys())

############################# SFD API ############################
API_SFD_SERVER = "https://mythologicinteractive.com/SFDGameServices.asmx"
SFD_REQUEST = """<?xml version='1.0' encoding='utf-8'?>
    <soap12:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'
     xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap12='http://www.w3.org/2003/05/soap-envelope'>
        <soap12:Body>
            <GetGameServers xmlns='https://mythologicinteractive.com/Games/SFD/'>
                <validationToken></validationToken>
            </GetGameServers>
        </soap12:Body>
    </soap12:Envelope>"""
SFD_HEADERS = {
    "Content-Type": "application/soap+xml; charset=utf-8",
    "SOAPAction": "https://mythologicinteractive.com/Games/SFD/GetGameServers",
}
