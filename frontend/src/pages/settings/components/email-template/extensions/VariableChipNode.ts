import { Node, mergeAttributes } from "@tiptap/core";

export const VariableChipNode = Node.create({
  name: "variableChip",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      variable: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-var"),
        renderHTML: (attributes) => ({ "data-var": attributes.variable }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-var]" }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        class: "var-chip",
        contenteditable: "false",
      }),
      node.attrs.variable ?? "",
    ];
  },
});
