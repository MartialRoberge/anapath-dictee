import { Fragment, memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Du Markdown rendu DANS une phrase, sans casser la ligne.
 *
 * La surface de travail affiche le compte rendu phrase par phrase, avec des
 * champs cliquables au milieu. Rendre chaque morceau avec le rendu Markdown
 * habituel l'enfermerait dans un paragraphe : chaque fragment passerait a la
 * ligne, et une phrase coupee par un trou se lirait sur trois lignes.
 *
 * On neutralise donc les enveloppes de bloc — paragraphe, titre, liste — et on
 * ne garde que ce qui se met en forme a l'interieur du texte : gras, italique,
 * code. Le compte rendu retrouve son apparence de compte rendu, au lieu
 * d'afficher ses etoiles et ses tirets bas.
 */

interface MarkdownEnLigneProps {
  texte: string;
}

/** Les enveloppes de bloc deviennent transparentes. */
const SANS_ENVELOPPE = {
  p: Fragment,
  h1: Fragment,
  h2: Fragment,
  h3: Fragment,
  h4: Fragment,
  h5: Fragment,
  h6: Fragment,
  ul: Fragment,
  ol: Fragment,
  li: Fragment,
  blockquote: Fragment,
} as const;

function MarkdownEnLigneBrut({ texte }: MarkdownEnLigneProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={SANS_ENVELOPPE}
      // Les liens sont desactives : un compte rendu n'en contient pas, et un
      // lien fabrique par un modele est une surface d'attaque gratuite.
      disallowedElements={["a", "img"]}
      unwrapDisallowed
    >
      {texte}
    </ReactMarkdown>
  );
}

export default memo(MarkdownEnLigneBrut);
