import { useTranslation } from "react-i18next";

export default function About() {
  const { t } = useTranslation();
  const sections = ["scoring", "cutoffs", "gcup", "identity", "coverage", "battles", "privacy"] as const;
  return (
    <article className="prose">
      <h1>{t("about.title")}</h1>
      <p className="lede">{t("about.lede")}</p>
      {sections.map((s) => (
        <section key={s}>
          <h2>{t(`about.${s}.title`)}</h2>
          <p>{t(`about.${s}.body`)}</p>
        </section>
      ))}
      <section>
        <h2>{t("about.credits.title")}</h2>
        <ul>
          <li>{t("about.credits.art")}</li>
          <li>{t("about.credits.names")}</li>
          <li>{t("about.credits.game")}</li>
          <li><a href="https://github.com/Lurpigi/DQMJ3P-Online" rel="noopener">{t("about.credits.source")}</a></li>
        </ul>
      </section>
    </article>
  );
}
