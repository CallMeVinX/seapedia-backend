"""
Message bodies for account-lifecycle email.

Every template ships an HTML and a plain-text variant. HTML-only mail is scored as spam by
most filters, and the text part is what actually renders in notification previews on mobile.
"""

BRAND = "Seapedia"
_ACCENT = "#0f766e"


def _wrap(inner: str) -> str:
    """
    Applies the shared shell to a message body.
    Styles are inlined rather than placed in a <style> block because Gmail strips embedded
    stylesheets, which would otherwise leave the message unstyled for most recipients.
    """
    return f"""\
<div style="margin:0;padding:24px;background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
  <div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:12px;padding:32px;">
    <div style="font-size:20px;font-weight:700;color:{_ACCENT};margin-bottom:24px;">{BRAND}</div>
    {inner}
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:28px 0 16px;">
    <div style="font-size:12px;color:#6b7280;line-height:1.6;">
      Email ini dikirim otomatis, mohon tidak membalas.<br>
      Jika Anda tidak merasa melakukan permintaan ini, abaikan saja email ini.
    </div>
  </div>
</div>"""


def registration_otp(full_name: str, code: str, expire_minutes: int) -> tuple[str, str, str]:
    """
    Builds the verification message carrying the registration OTP.
    Returns a (subject, html, text) triple; the code is repeated in the subject line so a user
    on mobile can read it from the notification without opening the message.
    """
    subject = f"{code} adalah kode verifikasi {BRAND} Anda"

    html = _wrap(f"""\
    <p style="font-size:15px;color:#111827;margin:0 0 8px;">Halo <strong>{full_name}</strong>,</p>
    <p style="font-size:15px;color:#374151;line-height:1.6;margin:0 0 24px;">
      Masukkan kode berikut untuk menyelesaikan pendaftaran akun {BRAND} Anda.
    </p>
    <div style="text-align:center;background:#f0fdfa;border:1px solid #99f6e4;border-radius:10px;padding:20px;margin-bottom:24px;">
      <div style="font-size:34px;font-weight:700;letter-spacing:10px;color:{_ACCENT};font-family:monospace;">{code}</div>
    </div>
    <p style="font-size:14px;color:#374151;line-height:1.6;margin:0;">
      Kode ini berlaku <strong>{expire_minutes} menit</strong> dan hanya dapat dipakai satu kali.
      Jangan bagikan kode ini kepada siapa pun, termasuk pihak yang mengaku dari {BRAND}.
    </p>""")

    text = (
        f"Halo {full_name},\n\n"
        f"Kode verifikasi pendaftaran {BRAND} Anda: {code}\n\n"
        f"Kode berlaku {expire_minutes} menit dan hanya dapat dipakai satu kali.\n"
        "Jangan bagikan kode ini kepada siapa pun.\n\n"
        "Jika Anda tidak merasa mendaftar, abaikan email ini."
    )
    return subject, html, text


def account_already_exists(email: str, login_url: str, reset_url: str) -> tuple[str, str, str]:
    """
    Notifies the owner of an address that someone attempted to register with it again.

    This exists so /auth/register can return an identical response whether or not the account
    exists, closing the enumeration hole, while the legitimate owner still learns why their
    OTP never arrived and is pointed at login or password recovery instead.
    """
    subject = f"Percobaan pendaftaran dengan email {BRAND} Anda"

    html = _wrap(f"""\
    <p style="font-size:15px;color:#111827;margin:0 0 8px;">Halo,</p>
    <p style="font-size:15px;color:#374151;line-height:1.6;margin:0 0 20px;">
      Ada yang mencoba mendaftar di {BRAND} menggunakan <strong>{email}</strong>,
      padahal alamat ini sudah terdaftar. Kami tidak membuat akun baru.
    </p>
    <p style="font-size:15px;color:#374151;line-height:1.6;margin:0 0 24px;">
      Jika itu Anda, silakan masuk seperti biasa. Lupa kata sandi? Gunakan tautan pemulihan.
    </p>
    <div style="margin-bottom:8px;">
      <a href="{login_url}" style="display:inline-block;background:{_ACCENT};color:#ffffff;text-decoration:none;padding:11px 22px;border-radius:8px;font-size:14px;font-weight:600;">Masuk ke akun</a>
      <a href="{reset_url}" style="display:inline-block;color:{_ACCENT};text-decoration:none;padding:11px 16px;font-size:14px;font-weight:600;">Atur ulang kata sandi</a>
    </div>""")

    text = (
        f"Halo,\n\n"
        f"Ada yang mencoba mendaftar di {BRAND} menggunakan {email}, "
        "padahal alamat ini sudah terdaftar. Tidak ada akun baru yang dibuat.\n\n"
        f"Masuk: {login_url}\n"
        f"Atur ulang kata sandi: {reset_url}\n\n"
        "Jika ini bukan Anda, tidak ada tindakan yang perlu dilakukan."
    )
    return subject, html, text
