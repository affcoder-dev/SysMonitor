# 🛡️ SysMonitor: Advanced Endpoint & HID Protection

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Zero_Trust-success.svg)
![Status](https://img.shields.io/badge/status-Active-brightgreen.svg)

**SysMonitor** is a robust Endpoint Detection and Response (EDR) prototype designed to secure personal and corporate computers against unauthorized external hardware threats. Moving beyond simple blocklists, SysMonitor operates on a strict **Zero-Trust** philosophy.

## ✨ Key Features

*   🔌 **Advanced Device Fingerprinting:** Verifies devices not just by easily spoofable VID/PID, but through unique **Windows USB Instance IDs**. A cloned device will still be detected and blocked.
*   ⌨️ **HID Spoofing & BadUSB Protection:** Prevents malicious scripts disguised as keyboards (like Rubber Ducky). Unrecognized HID devices trigger an immediate **Password Challenge**, freezing inputs until authorized.
*   🚫 **Default-Deny Policy:** Unlisted USB storage units are completely blocked from reading or writing data.
*   ⚡ **Real-Time PnP Listening:** Intercepts Plug and Play (PnP) events at the millisecond level, neutralizing threats before Windows can even mount the device.
*   🤫 **Silent Authorization:** Automatically suppresses annoying Windows prompts ("Format this drive", etc.) for whitelisted devices, ensuring a seamless user experience.

---

*Developed by [affcoder]*

<br>

---
---

# 🛡️ SysMonitor: Gelişmiş Uç Nokta ve HID Koruması (Türkçe)

**SysMonitor**, kişisel ve kurumsal bilgisayarları yetkisiz harici donanım tehditlerine karşı korumak için tasarlanmış güçlü bir EDR (Uç Nokta Tespiti ve Yanıtı) prototipidir. Basit bir engelleyici olmanın ötesine geçen SysMonitor, katı bir **Sıfır Güven (Zero-Trust)** felsefesiyle çalışır.

## ✨ Temel Özellikler

*   🔌 **Gelişmiş Cihaz Tanıma (Fingerprinting):** Cihazları yalnızca kolayca taklit edilebilen (spoofing) VID/PID bilgileriyle değil, benzersiz **Windows USB Instance ID**'lerine göre doğrular. Klonlanmış bir cihaz dahi anında tespit edilir ve engellenir.
*   ⌨️ **HID Sahteciliği ve BadUSB Koruması:** Klavye kılığına giren (Rubber Ducky vb.) zararlı yazılımları engeller. Tanınmayan HID cihazları takıldığında sistem anında bir **Parola Doğrulama (Password Challenge)** ekranı çıkararak, yetki verilene kadar tüm girişleri dondurur.
*   🚫 **Sıfır Tolerans Politikası:** Beyaz listede (whitelist) yer almayan hiçbir USB depolama birimi sisteme veri yazamaz veya sistemden veri okuyamaz.
*   ⚡ **Gerçek Zamanlı PnP Dinleme:** Tak-Çalıştır (PnP) olaylarını milisaniye seviyesinde dinleyerek, donanım daha Windows üzerinde görünmeden (mount edilmeden) tehditleri etkisiz hale getirir.
*   🤫 **Sessiz Yetkilendirme:** Güvenilir cihazlar için Windows'un can sıkıcı uyarılarını ("Bu diski biçimlendir" vb.) arka planda otomatik olarak bastırır ve pürüzsüz bir kullanıcı deneyimi sunar.

---

*[affcoder] tarafından geliştirilmiştir.*