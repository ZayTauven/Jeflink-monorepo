/**
 * Menu de la console : une seule source pour la barre latérale, la recherche (Ctrl K) et les
 * pages « bientôt ». `lot` = lot de livraison d'une rubrique pas encore construite.
 */
import type { ConsoleSection } from "@/lib/types";

import type { Badges } from "./types";

export type NavItem = {
  href: string;
  label: string;
  icon: string; // classe Bootstrap Icons (police d'icônes Crafto)
  /** Pastille : un compteur, ou la somme de plusieurs. */
  badge?: keyof Badges | (keyof Badges)[];
  lot?: number;
  summary?: string;
  keywords?: string[];
  section?: ConsoleSection; // remplace celle de la section du menu
};

export type NavSection = { title: string; section: ConsoleSection; items: NavItem[] };

export const NAV: NavSection[] = [
  {
    title: "Pilotage",
    section: "dashboard",
    items: [
      {
        href: "/console",
        label: "Tableau de bord",
        icon: "bi-speedometer2",
        keywords: ["accueil", "chiffres", "kpi"],
      },
      {
        href: "/console/rapports",
        section: "finance",
        label: "Rapports",
        icon: "bi-graph-up-arrow",
        summary:
          "Six derniers mois : missions, volume, remises, commissions ; détail par métier ; export CSV.",
        keywords: ["export", "statistiques"],
      },
    ],
  },
  {
    title: "Opérations",
    section: "operations",
    items: [
      {
        href: "/console/demandes",
        label: "Demandes",
        icon: "bi-inbox",
        badge: ["cancel_requests", "stale_requests"],
        summary:
          "Toutes les demandes, filtrées par statut, métier, quartier et date ; historique, devis et note interne.",
        keywords: ["missions", "devis", "réservations"],
      },
      {
        href: "/console/litiges",
        label: "Litiges",
        icon: "bi-exclamation-triangle",
        badge: "disputes_active",
        summary: "Signalements d'un client ou d'un pro, suivi jusqu'à la résolution.",
        keywords: ["réclamations", "signalements"],
      },
    ],
  },
  {
    title: "Communauté",
    section: "operations",
    items: [
      {
        href: "/console/pros",
        label: "Pros",
        icon: "bi-person-badge",
        badge: "pros_pending",
        summary:
          "File de vérification des nouveaux pros, fiches, métiers et quartiers, suspension.",
        keywords: ["prestataires", "vérification", "artisans"],
      },
      {
        href: "/console/clients",
        label: "Clients",
        icon: "bi-people",
        summary: "Comptes clients, demandes passées, dépenses, blocage.",
        keywords: ["utilisateurs", "comptes"],
      },
      {
        href: "/console/avis",
        label: "Avis",
        icon: "bi-star-half",
        summary: "Modération des avis : masquer un avis abusif, répondre aux notes basses.",
        keywords: ["notes", "modération"],
      },
      {
        href: "/console/messages",
        label: "Messages",
        icon: "bi-chat-left-text",
        badge: "contact_unhandled",
        summary: "Messages envoyés depuis la page Contact, à traiter par l'équipe.",
        keywords: ["contact", "support"],
      },
    ],
  },
  {
    title: "Catalogue",
    section: "catalog",
    items: [
      {
        href: "/console/metiers",
        label: "Métiers",
        icon: "bi-grid-3x3-gap",
        summary:
          "Métiers, prestations courantes, prix « à partir de », image et ordre d'affichage.",
        keywords: ["services", "catégories"],
      },
      {
        href: "/console/quartiers",
        label: "Quartiers",
        icon: "bi-geo-alt",
        summary: "Quartiers et communes desservis, ouverture d'une nouvelle zone.",
        keywords: ["zones", "villes"],
      },
    ],
  },
  {
    title: "Marketing",
    section: "marketing",
    items: [
      {
        href: "/console/promos",
        label: "Codes promo",
        icon: "bi-ticket-perforated",
        summary:
          "Remises en % ou en F CFA, plafond, dates, nombre d'utilisations, ciblage métier, quartier ou premier achat. Financées par Jeflink.",
        keywords: ["coupons", "réductions", "remises"],
      },
      {
        href: "/console/campagnes",
        label: "Campagnes",
        icon: "bi-megaphone",
        summary: "Bannières et annonces affichées sur le site, avec période et emplacement.",
        keywords: ["bannières", "annonces", "publicité"],
      },
    ],
  },
  {
    title: "Finances",
    section: "finance",
    items: [
      {
        href: "/console/transactions",
        label: "Transactions",
        icon: "bi-cash-coin",
        summary: "Missions terminées : montant du devis, remise, commission Jeflink, net du pro.",
        keywords: ["paiements", "chiffre d'affaires"],
      },
      {
        href: "/console/commissions",
        label: "Commissions",
        icon: "bi-percent",
        summary: "Taux de commission par défaut et par métier.",
        keywords: ["revenus", "taux"],
      },
      {
        href: "/console/soldes",
        label: "Soldes des pros",
        icon: "bi-wallet2",
        summary: "Ce que chaque pro doit à Jeflink (ou l'inverse) et les règlements reçus.",
        keywords: ["reversements", "paiements pros"],
      },
    ],
  },
  {
    title: "Jef · IA",
    section: "operations",
    items: [
      {
        href: "/console/jef",
        label: "Jef",
        icon: "bi-stars",
        summary:
          "L'assistant qui aide le client à décrire son souci et transmet une fiche claire au pro : réglages, conversations, indicateurs.",
        keywords: ["ia", "assistant", "booking"],
      },
    ],
  },
  {
    title: "Administration",
    section: "admin",
    items: [
      {
        href: "/console/equipe",
        label: "Équipe et rôles",
        icon: "bi-shield-lock",
        summary: "Comptes de l'équipe et rôles : Opérations, Marketing, Finance, Super admin.",
        keywords: ["staff", "permissions", "accès"],
      },
      {
        href: "/console/reglages",
        label: "Réglages",
        icon: "bi-sliders",
        summary: "Nombre de devis par demande, numéro WhatsApp du support, commission par défaut.",
        keywords: ["paramètres", "configuration"],
      },
      {
        href: "/console/journal",
        section: "operations",
        label: "Journal des actions",
        icon: "bi-journal-text",
        summary: "Qui a fait quoi dans la console, et quand.",
        keywords: ["historique", "audit", "traces"],
      },
    ],
  },
];

export const NAV_ITEMS = NAV.flatMap((s) =>
  s.items.map((i) => ({ ...i, section: i.section ?? s.section })),
);

/** Le menu limité aux rubriques ouvertes au rôle de la personne connectée. */
export function navFor(sections: ConsoleSection[]): NavSection[] {
  return NAV.map((s) => ({
    ...s,
    items: s.items.filter((i) => sections.includes(i.section ?? s.section)),
  })).filter((s) => s.items.length > 0);
}

export function findNavItem(href: string): NavItem | undefined {
  return NAV_ITEMS.find((i) => i.href === href);
}
