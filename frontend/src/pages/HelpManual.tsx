import { useEffect, useState } from 'react';
import type { Lang } from '../i18n/translations';

type Props = { lang: Lang };

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
};

export default function HelpManual({ lang }: Props) {
  const mr = lang === 'mr';
  const [installPrompt, setInstallPrompt] = useState<InstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    const checkInstalled = () => {
      const standalone = window.matchMedia('(display-mode: standalone)').matches ||
        (window.navigator as any).standalone === true;
      setInstalled(standalone);
    };
    checkInstalled();

    const beforeInstall = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as InstallPromptEvent);
    };
    const appInstalled = () => {
      setInstalled(true);
      setInstallPrompt(null);
    };
    window.addEventListener('beforeinstallprompt', beforeInstall);
    window.addEventListener('appinstalled', appInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', beforeInstall);
      window.removeEventListener('appinstalled', appInstalled);
    };
  }, []);

  async function installApp() {
    if (!installPrompt) return;
    await installPrompt.prompt();
    await installPrompt.userChoice;
    setInstallPrompt(null);
  }

  return (
    <main className="content">
      <div className="page-title">
        <div>
          <h2>{mr ? 'मदत व वापरकर्ता मार्गदर्शिका' : 'Help & User Manual'}</h2>
          <p>{mr ? 'PM POSHAN v1.0 ची मराठी + English मार्गदर्शिका आणि ॲप इंस्टॉलेशन.' : 'PM POSHAN v1.0 bilingual user manual and app installation.'}</p>
        </div>
      </div>

      <section className="panel">
        <h3>{mr ? 'वापरकर्ता मार्गदर्शिका PDF' : 'User Manual PDF'}</h3>
        <p>{mr
          ? 'डेटा कुठे भरायचा, पडताळणी कशी करायची, साठा आणि अहवाल कसे तयार होतात याचे संपूर्ण वर्णन या मार्गदर्शिकेत आहे.'
          : 'The manual explains where to enter each type of data, verification workflow, stock processing and report generation.'}</p>
        <div className="action-row">
          <a className="primary button-link" href="/docs/PM_POSHAN_User_Manual_Bilingual_v1.0.pdf" target="_blank" rel="noreferrer">
            {mr ? 'PDF उघडा' : 'Open PDF'}
          </a>
          <a className="secondary button-link" href="/docs/PM_POSHAN_User_Manual_Bilingual_v1.0.pdf" download>
            {mr ? 'PDF डाउनलोड करा' : 'Download PDF'}
          </a>
        </div>
      </section>

      <section className="panel">
        <h3>{mr ? 'Windows / Android वर ॲप इंस्टॉल करा' : 'Install on Windows / Android'}</h3>
        {installed ? (
          <div className="notice">{mr ? 'PM POSHAN हे ॲप म्हणून चालू आहे.' : 'PM POSHAN is currently running as an installed app.'}</div>
        ) : installPrompt ? (
          <div className="action-row">
            <button className="primary" onClick={installApp}>{mr ? 'PM POSHAN इंस्टॉल करा' : 'Install PM POSHAN'}</button>
          </div>
        ) : (
          <div className="notice">
            {mr
              ? 'इंस्टॉल बटण दिसत नसल्यास HTTPS वर ॲप उघडा. Android Chrome मध्ये “Add to Home screen / Install app”, आणि Windows Edge/Chrome मध्ये “Install this site as an app” वापरा.'
              : 'If the install button is not available, open the site over HTTPS. On Android Chrome use “Add to Home screen / Install app”; on Windows Edge/Chrome use “Install this site as an app”.'}
          </div>
        )}
      </section>

      <section className="panel">
        <h3>{mr ? 'महत्त्वाची टीप' : 'Important note'}</h3>
        <p>{mr
          ? 'PWA इंस्टॉल झाल्यानंतरही दैनिक डेटा, पडताळणी आणि साठा व्यवहारांसाठी सर्व्हरशी इंटरनेट/नेटवर्क कनेक्शन आवश्यक आहे. पूर्ण ऑफलाइन डेटा-सिंक हा स्वतंत्र पुढील टप्पा आहे.'
          : 'Installing the PWA does not make operational data fully offline. Daily entry, verification and stock transactions still require network access to the server. Full offline synchronization is a separate future phase.'}</p>
      </section>
    </main>
  );
}
