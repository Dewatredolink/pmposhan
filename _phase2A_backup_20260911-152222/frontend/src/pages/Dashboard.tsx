import { Lang, t } from '../i18n/translations';

type Props = { lang: Lang };
export default function Dashboard({lang}: Props) {
  const tr = (k: keyof typeof t) => t[k][lang];
  const cards = [
    [tr('students'),'200'],[tr('presentToday'),'—'],[tr('mealsToday'),'—'],[tr('mealsMonth'),'—']
  ];
  return <main className="content">
    <section className="cards">{cards.map(([label,value]) => <article className="card" key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
    <h2>{tr('inventory')}</h2>
    <section className="cards small">
      <article className="card"><span>{tr('rice')}</span><strong>— KG</strong></article>
      <article className="card"><span>{tr('dal')}</span><strong>— KG</strong></article>
      <article className="card"><span>{tr('oil')}</span><strong>— L</strong></article>
      <article className="card"><span>{tr('eggs')}</span><strong>—</strong></article>
    </section>
    <section className="panel"><h2>{tr('alerts')}</h2><p>{lang==='mr'?'सध्या कोणतीही सूचना नाही.':'No alerts at present.'}</p></section>
  </main>
}
