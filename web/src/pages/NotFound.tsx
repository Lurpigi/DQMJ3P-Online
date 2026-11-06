import { useTranslation } from "react-i18next";
import { L } from "../components/L";

export default function NotFound() {
  const { t } = useTranslation();
  return <div className="empty"><h1>{t("state.notFound")}</h1><p><L to="/">{t("nav.overview")}</L></p></div>;
}
