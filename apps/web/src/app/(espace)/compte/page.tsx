import { redirect } from "next/navigation";

// /compte n'a pas d'écran propre : l'espace du client commence par ses demandes.
export default function AccountPage() {
  redirect("/compte/demandes");
}
