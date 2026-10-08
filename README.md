# ID Card Desk (Django version)

School ID card system: admin, team members, schools, photo day, parent OTP verification,
school approval, print queue, per-school card templates, PDF cards, class-wise reports.

Is README me har step "ye karo, ye command chalao" ke format me hai.

---

## Step 0. Kya chahiye

- Python 3.11 ya naya (python.org se install karo; Windows par "Add Python to PATH" tick karo)
- Ek terminal (Windows: Command Prompt ya PowerShell, Mac/Linux: Terminal)

## Step 1. Project folder kholo

Zip ko extract karo, phir terminal me us folder me jao (jisme `manage.py` hai):

    cd idcards

## Step 2. Virtual environment banao aur libraries install karo

Windows:

    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt

Mac / Linux:

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

## Step 3. Database banao

    python manage.py migrate

(Local par SQLite use hota hai, kuch set karna nahi padta.)

## Step 4. Apna admin (owner) login banao

    python manage.py create_admin aapka@email.com --name "Aapka Naam"

## Step 5. Server chalao

    python manage.py runserver

Browser me kholo: http://127.0.0.1:8000/login/

Email daalo. Development me OTP **terminal me print hota hai aur screen par bhi dikhta hai**
(`DEBUG=1` hone par). Production me yeh screen par kabhi nahi dikhta.

## Step 6. Pehli baar ka setup (browser me)

1. **Dashboard > Add a school**: school ka naam aur uska login email. Us email par school OTP se login karega.
2. **Card design** (school ke saamne): school ka card template image upload karo, size (mm) dalo, phir har field ka dabba drag karke sahi jagah rakho. "Sample card PDF" se check karo.
3. **Team members**: naam + email jodo, schools tick karke allot karo.
4. School login karke:
   - "Fields on the ID card" me jo chahiye tick karo (Father/Mother photo bhi).
   - CSV upload karo (template download karke) ya ek-ek student add karo.
   - **Photo day** tab: admission no daalo, camera ya upload se photo lo (server par 4:5 me crop + compress hoti hai).
   - Student ke saamne **Send link on WhatsApp**: parent ko verification link jata hai.
5. Parent link kholta hai: card dekhta hai, galat details sudharta hai, photo badal sakta hai, mobile par aaye OTP se verify karta hai.
6. School **OK, send for print** dabata hai (ya "OK all verified" bulk me).
7. Admin **Print queue** me PDF nikalta hai, **Mark printed / Mark delivered** karta hai.

## Step 7. Tests chalao (code sahi chal raha hai ya nahi)

    python manage.py test core

Yeh poora flow test karta hai: OTP login, school/team access, CSV, photo, parent OTP, approval, PDF, reports.

## Step 8. Internet par daalna: Render (managed service)

Render ek managed service hai: server aapko khud nahi sambhalna padta. Yeh steps Render ke dashboard ke hain;
unke button ke naam kabhi badal sakte hain, isliye kuch alag dikhe to Render ke docs dekh lena.

**8.1 Code GitHub par rakho**
1. github.com par free account banao, ek **private** repository banao (bachchon ka data wala code private hi rakho).
2. Is folder ka code us repo me upload karo (`git push`, ya GitHub ka "upload files").
   `.gitignore` me `db.sqlite3`, `media/`, `.env` pehle se hain, yeh upload nahi honge.

**8.2 Database banao**
1. render.com par account banao > **New > PostgreSQL**.
2. Naam: `idcards-db`. Plan: **paid plan lo**. Free database kuch din baad expire ho jata hai
   (Render ke pricing page par free Postgres ki 30 din ki limit likhi hai). Asli data free database me mat rakho.
3. Banne ke baad **Internal Database URL** copy karke rakho.

**8.3 Web service banao**
1. **New > Web Service**, apni GitHub repo chuno.
2. Language: **Python**. Region: database wala hi region.
3. Build Command:

       ./build.sh

   Start Command:

       gunicorn config.wsgi

4. Instance type: **paid (Starter ya usse upar)**. Free web service par photos ke liye disk nahi lag sakti
   aur woh 15 minute idle rehne par so jati hai.

**8.4 Photos ke liye disk lagao (zaroori)**
1. Web service > **Disks > Add Disk**. Name: `media`. Mount path: `/var/data`. Size: 5 GB se shuru karo (badha sakte ho).
2. Disk ke bina har deploy par saari photos aur templates mit jayengi.

**8.5 Environment variables** (Web service > Environment)

| Key | Value |
|---|---|
| `DEBUG` | `0` |
| `SECRET_KEY` | lambi random string (kisi ko mat batao) |
| `DATABASE_URL` | step 8.2 ka Internal Database URL |
| `MEDIA_ROOT` | `/var/data/media` |
| `ADMIN_EMAIL` | aapka email (is par admin login ban jayega) |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | email service ki details (Step 9). **Iske bina OTP email nahi jayega** |

`ALLOWED_HOSTS` aur `CSRF_TRUSTED_ORIGINS` Render ka apna address (`RENDER_EXTERNAL_HOSTNAME`) khud jod leta hai.
Apna domain lagaoge to `ALLOWED_HOSTS` me us domain ko bhi likho aur `CSRF_TRUSTED_ORIGINS=https://aapka-domain`.
Python version `.python-version` file se 3.12 tay hai.

**8.6 Deploy**
1. **Create Web Service / Manual Deploy** dabao. Build me 2 se 5 minute lagte hain.
2. Khulne par `https://aapka-service.onrender.com/login/` kholo. `ADMIN_EMAIL` daalo, OTP email se aayega.
3. Custom domain ke liye Render me **Settings > Custom Domains**; HTTPS wahi laga deta hai.

**8.7 Deploy ke baad zaroor check karo**
- Ek test school banao, photo upload karo, ek deploy dobara karo, aur dekho photo bachi hai ya nahi (disk sahi laga hai ya nahi).
- Database ka backup/restore option Render me dekh lo, aur roz ka backup chalu rakho.
- Kharcha: web service + database + disk teeno ka mahina alag-alag judta hai. Render ke pricing page par abhi ka rate dekh lo.

## Step 9. Asli OTP bhejna

- **Email OTP** (school, team, admin login): SMTP service lo (Brevo, Amazon SES, Gmail Workspace) aur set karo:
  `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`.
- **Parent mobile OTP**: abhi `core/otp.py` me `send_sms()` provider ke bina sirf log karta hai.
  Apne SMS ya WhatsApp provider ke liye ek function likho (`core/sms_example.py` dekho, yeh sirf namuna hai,
  kisi provider par test nahi kiya) aur `SMS_SENDER=core.sms_example.send` set karo.
  India me SMS ke liye provider ke paas DLT template register karwana padta hai.

## Step 10. Hindi ya doosri script ka naam card par

Default font sirf English letters chhapta hai. Doosri script ke liye ek `.ttf` font file rakho
(jaise Noto Sans Devanagari) aur `CARD_FONT=/path/to/font.ttf` set karo.
Dhyan do: reportlab Devanagari ke jude akshar (conjuncts) sahi shape nahi karta. Pure Hindi naam ke liye
agla upgrade WeasyPrint se HTML-to-PDF hoga.

---

## Suraksha aur privacy (zaroor padho)

- Yeh **bachchon ka data** hai. Schools se likhit anumati, privacy policy, aur parent ki sahmati ka tareeka tay karo
  (India me DPDP Act 2023). Kisi vakil se ek baar poochh lo.
- Photos public URL par nahi hain. Sirf login kiye hue allowed log, ya us student ka parent link, unhe dekh sakta hai.
- Parent link ek lamba random token hai. Link ko public jagah share mat karo.
- OTP 6 digit, 5 minute valid, 3 galat try par lock, naya code 20 second baad.
- Database ka roz backup lo (Render PostgreSQL me backup option hota hai).
- Production me `DEBUG=0` zaroor rakho.

## Demo se kya alag hai

- Data ab server database me hai: sab log (admin, team, school, parent) ek hi data dekhte hain.
- Built-in header wale layouts nahi hain. Har school ka apna template image aur field positions hain
  (image na ho to saada safed card banta hai).
- Telegram aur WhatsApp Business API abhi nahi hain. WhatsApp ke liye `wa.me` link use hota hai
  (school staff ke phone se bhejna padta hai).
- Student edit/delete ke liye abhi alag screen nahi hai. `python manage.py createsuperuser` banao aur
  `/django-admin/` use karo.
- Admin ka login bhi email OTP se hai (`create_admin` command).

## Folder ka naksha

    config/            settings, urls
    core/models.py     School, Member, Student, OTP
    core/views.py      saare pages aur actions
    core/layout.py     card par kaunsi cheez kahan baithti hai
    core/pdfcards.py   card PDF banana
    core/photos.py     photo crop + compress
    core/otp.py        OTP banana / jaanchna / bhejna
    core/templates/    HTML pages
    core/tests.py      automatic tests
