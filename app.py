from flask import Flask, render_template, request, redirect, url_for, session
import os
import xml.etree.ElementTree as ET
import datetime
import json
from werkzeug.utils import secure_filename

app = Flask(__name__, static_url_path='/DGUVV3/static')
app.secret_key = "supersecretkey"

DATA_FOLDER = os.path.join(os.path.dirname(__file__), "data")
UPLOAD_FOLDER = DATA_FOLDER
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def lade_benutzer():
    try:
        with open(os.path.join(DATA_FOLDER, 'users.json'), encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Fehler beim Laden der Benutzer: {e}")
        return []


def letzter_xml_name():
    files = sorted(
        [f for f in os.listdir(DATA_FOLDER) if f.endswith('.xml')],
        key=lambda x: os.path.getmtime(os.path.join(DATA_FOLDER, x)),
        reverse=True
    )
    return files[0] if files else None


def zellen_als_dict(row, ns):
    zellen = {}
    aktuelle_spalte = 1
    for cell in row.findall("ss:Cell", ns):
        index_attr = cell.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
        if index_attr:
            aktuelle_spalte = int(index_attr)
        data = cell.find("ss:Data", ns)
        zellen[aktuelle_spalte] = data.text if data is not None else ""
        aktuelle_spalte += 1
    return zellen


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        benutzer = request.form.get("benutzer")
        passwort = request.form.get("passwort")
        for user in lade_benutzer():
            if user["benutzer"] == benutzer and user["passwort"] == passwort:
                session["benutzer"] = benutzer
                return redirect(url_for("index"))
        return "Login fehlgeschlagen"
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def index():
    if "benutzer" not in session:
        return redirect(url_for("login"))

    filename = letzter_xml_name()
    ersatzteil_path = os.path.join(DATA_FOLDER, "ersatzteile.json")

    ns = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
    gruen, gelb, rot, privat = [], [], [], []

    if filename:
        try:
            tree = ET.parse(os.path.join(DATA_FOLDER, filename))
            root = tree.getroot()
            rows = root.findall(".//ss:Worksheet/ss:Table/ss:Row", ns)

            for row in rows[1:]:
                zellen = zellen_als_dict(row, ns)
                try:
                    id_text = zellen.get(11)
                    geraet = zellen.get(3, "-")
                    abteilung = zellen.get(5, "-")
                    naechste = zellen.get(14, "-")
                    status_text = zellen.get(19, "false")  # Spalte S

                    if not id_text or not id_text.isdigit():
                        continue

                    eintrag_id = int(id_text)
                    datum_text = naechste.split()[0] if naechste and " " in naechste else naechste
                    pruefdatum = datetime.datetime.strptime(datum_text, "%d.%m.%Y")
                    diff = (pruefdatum - datetime.datetime.today()).days

                    eintrag = {
                        "id": eintrag_id,
                        "geraet": geraet,
                        "abteilung": abteilung,
                        "naechste": naechste
                    }

                    if status_text.lower() == "true":
                        privat.append(eintrag)

                    # Ampel unabhängig vom Status
                    if diff < 0:
                        rot.append(eintrag)
                    elif diff <= 30:
                        gelb.append(eintrag)
                    else:
                        gruen.append(eintrag)

                except Exception as e:
                    print(f"Fehler bei Eintrag: {e}")
        except Exception as e:
            print(f"Fehler beim Parsen der XML-Datei: {e}")

    ersatzteile = []
    if os.path.exists(ersatzteil_path):
        try:
            with open(ersatzteil_path, encoding="utf-8") as f:
                ersatzteile = json.load(f)
        except:
            pass

    return render_template("management.html",
                           heute=datetime.datetime.today().strftime("%d.%m.%Y"),
                           gruen=gruen,
                           gelb=gelb,
                           rot=rot,
                           privat=privat,
                           anzahl_gruen=len(gruen),
                           anzahl_gelb=len(gelb),
                           anzahl_rot=len(rot),
                           anzahl_privat=len(privat),
                           ersatzteile=ersatzteile,
                           benutzername=session['benutzer'])


@app.route("/upload_datenbank", methods=["POST"])
def upload_datenbank():
    if "datenbank" not in request.files:
        return "Keine Datei ausgewählt"
    datei = request.files["datenbank"]
    if datei and datei.filename.endswith(".xml"):
        filename = secure_filename(datei.filename)
        pfad = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        datei.save(pfad)
        return redirect(url_for("index"))
    return "Ungültige Datei"


@app.route("/update_lager", methods=["POST"])
def update_lager():
    ersatzteil_path = os.path.join(DATA_FOLDER, "ersatzteile.json")
    teilname = request.form.get("teil")
    aktion = request.form.get("aktion")
    try:
        with open(ersatzteil_path, encoding="utf-8") as f:
            lager = json.load(f)
        for teil in lager:
            if teil["teil"] == teilname:
                if aktion == "+":
                    teil["bestand"] += 1
                elif aktion == "-" and teil["bestand"] > 0:
                    teil["bestand"] -= 1
                break
        with open(ersatzteil_path, "w", encoding="utf-8") as f:
            json.dump(lager, f, indent=2)
    except:
        pass
    return redirect(url_for("index"))


@app.route("/add_teil", methods=["POST"])
def add_teil():
    ersatzteil_path = os.path.join(DATA_FOLDER, "ersatzteile.json")
    name = request.form.get("new_name")
    bestand = int(request.form.get("new_bestand"))
    typ = request.form.get("new_typ")
    try:
        with open(ersatzteil_path, encoding="utf-8") as f:
            lager = json.load(f)
        lager.append({"teil": name, "bestand": bestand, "geraetetyp": typ})
        with open(ersatzteil_path, "w", encoding="utf-8") as f:
            json.dump(lager, f, indent=2)
    except:
        pass
    return redirect(url_for("index"))


@app.route("/suche_nach_id", methods=["GET"])
def suche_nach_id():
    if "benutzer" not in session:
        return redirect(url_for("login"))

    suchbegriff = request.args.get("such_id", "").strip()
    filename = letzter_xml_name()
    ns = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}

    if not filename or not suchbegriff:
        return "Keine gültige Eingabe oder Datei gefunden."

    try:
        tree = ET.parse(os.path.join(DATA_FOLDER, filename))
        root = tree.getroot()
        rows = root.findall(".//ss:Worksheet/ss:Table/ss:Row", ns)

        suchergebnisse = []

        for row in rows[1:]:
            zellen = zellen_als_dict(row, ns)
            id_text = zellen.get(11)
            geraet = zellen.get(3, "-")
            abteilung = zellen.get(5, "-")
            pruefdatum = zellen.get(14, "-")

            if suchbegriff.isdigit() and id_text == suchbegriff:
                suchergebnisse.append({
                    "id": id_text,
                    "geraet": geraet,
                    "abteilung": abteilung,
                    "pruefdatum": pruefdatum
                })
                break
            elif abteilung and suchbegriff.lower() in abteilung.lower():
                suchergebnisse.append({
                    "id": id_text,
                    "geraet": geraet,
                    "abteilung": abteilung,
                    "pruefdatum": pruefdatum
                })

        abteilungsanzahl = len(suchergebnisse) if not suchbegriff.isdigit() else None

        return render_template(
            "suchergebnis.html",
            suchbegriff=suchbegriff,
            ergebnisse=suchergebnisse,
            abteilungsanzahl=abteilungsanzahl
        )

    except Exception as e:
        return f"Fehler bei der Suche: {e}"


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
