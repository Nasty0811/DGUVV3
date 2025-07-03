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


# Benutzerprüfung
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
    gruen, gelb, rot = [], [], []

    if filename:
        try:
            tree = ET.parse(os.path.join(DATA_FOLDER, filename))
            root = tree.getroot()
            rows = root.findall(".//ss:Worksheet/ss:Table/ss:Row", ns)

            for i, row in enumerate(rows[1:], 1):
                zellen = row.findall("ss:Cell/ss:Data", ns)
                try:
                    geraet = zellen[2].text if len(zellen) > 2 else "-"
                    abteilung = zellen[4].text if len(zellen) > 4 else "-"
                    naechste = zellen[13].text if len(zellen) > 13 else "-"

                    datum_text = naechste.split()[0]
                    pruefdatum = datetime.datetime.strptime(datum_text, "%d.%m.%Y")
                    diff = (pruefdatum - datetime.datetime.today()).days

                    eintrag = {
                        "id": i,
                        "geraet": geraet,
                        "abteilung": abteilung,
                        "naechste": naechste
                    }

                    if diff < 0:
                        rot.append(eintrag)
                    elif diff <= 30:
                        gelb.append(eintrag)
                    else:
                        gruen.append(eintrag)
                except:
                    continue
        except Exception as e:
            print(f"Fehler beim Parsen der XML-Datei: {e}")

    # Ersatzteillager
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
                           anzahl_gruen=len(gruen),
                           anzahl_gelb=len(gelb),
                           anzahl_rot=len(rot),
                           ersatzteile=ersatzteile,
                           benutzername=session['benutzer'])  # <– Anpassung hier


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


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")

