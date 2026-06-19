import resend
from app.config import settings

resend.api_key = settings.resend_api_key

async def send_password_email(to_email: str, password: str):
    resend.Emails.send({
        "from": settings.resend_from,
        "to": to_email,
        "subject": "Kata Laluan ResearcherHQ Anda",
        "html": f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
          <h2 style="color: #1C1B19;">Kata Laluan Anda</h2>
          <p>Gunakan kata laluan berikut untuk log masuk ke ResearcherHQ:</p>
          <div style="background: #F8F6F1; padding: 16px; border-radius: 8px;
                      font-family: monospace; font-size: 24px; letter-spacing: 4px;
                      text-align: center; color: #1C1B19;">
            {password}
          </div>
          <p style="color: #4A463F; font-size: 13px; margin-top: 16px;">
            Kata laluan ini dijana khas untuk anda. Simpan dengan selamat.
            Jika bukan anda yang minta, abaikan emel ini.
          </p>
        </div>
        """
    })
