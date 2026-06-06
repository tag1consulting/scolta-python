"""Build a partial inverted index for a chunk of content items.

Port of ``Tag1\\Scolta\\Index\\InvertedIndexBuilder``. Each chunk produces a
word -> pages mapping with positions and weights; multiple chunks are later
merged by IndexMerger into a complete index. Title weight 50, body weight 25,
200-position cap per weight bucket per page; positions are reindexed to
word-sequential indices.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit

from .. import html as htmlmod
from .token import Token

TITLE_WEIGHT = 50
BODY_WEIGHT = 25
MAX_POSITIONS_PER_WEIGHT = 200

_TITLE_SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_URL_EXT = re.compile(r"\.\w+$")


class InvertedIndexBuilder:
    TITLE_WEIGHT = TITLE_WEIGHT
    BODY_WEIGHT = BODY_WEIGHT
    MAX_POSITIONS_PER_WEIGHT = MAX_POSITIONS_PER_WEIGHT

    def __init__(self, tokenizer, stemmer) -> None:
        self.tokenizer = tokenizer
        self.stemmer = stemmer

    def build(self, items, page_offset: int = 0) -> dict:
        token_data_list = []
        for item in items:
            td = self.tokenize_item(item)
            if td is not None:
                token_data_list.append({"item": item, "tokenData": td})
        return self.build_from_token_data(token_data_list, page_offset)

    def tokenize_item(self, item) -> dict | None:
        clean_text = htmlmod.clean(item.body_html, item.title)
        if len(clean_text) < 10:
            return None

        title_raw = _TITLE_SCRIPT_STYLE.sub("", item.title)
        clean_title = htmlmod.decode_entities(htmlmod.strip_tags(title_raw))

        raw_title_tokens = self.tokenizer.tokenize(clean_title)
        title_tokens, next_index = self._reindex(raw_title_tokens, 0)

        raw_body_tokens = self.tokenizer.tokenize(clean_text)
        body_tokens, next_index = self._reindex(raw_body_tokens, next_index)

        url_path = urlsplit(item.url).path or ""
        url_path = _URL_EXT.sub("", url_path)
        url_segments = [s for s in url_path.split("/") if len(s) > 0]
        url_text = " ".join(url_segments)
        raw_url_tokens = self.tokenizer.tokenize(url_text)
        url_tokens, _ = self._reindex(raw_url_tokens, next_index)

        word_count = len(title_tokens) + len(body_tokens)
        content = clean_title + ". " + clean_text if clean_title != "" else clean_text

        return {
            "titleTokens": title_tokens,
            "bodyTokens": body_tokens,
            "urlTokens": url_tokens,
            "wordCount": word_count,
            "cleanTitle": clean_title,
            "content": content,
        }

    def build_from_token_data(self, token_data_list, page_offset: int = 0) -> dict:
        index: dict = {}
        pages: dict = {}
        page_num = page_offset

        for entry in token_data_list:
            item = entry["item"]
            td = entry["tokenData"]

            item_sortable = dict(getattr(item, "sortable", None) or {})
            item_date = getattr(item, "date", "") or ""
            if item_date != "" and "date" not in item_sortable:
                item_sortable["date"] = item_date

            filters: dict = {}
            if item.site_name != "":
                filters["site"] = item.site_name
            if item.language != "":
                filters["language"] = item.language
            filters.update(item.filters)

            # PHP: ['title'=>.., 'date'=>..] + itemSortable (left keys win),
            # then array_filter removes null/'' values.
            combined = {"title": td["cleanTitle"], "date": item.date}
            for k, v in item_sortable.items():
                if k not in combined:
                    combined[k] = v
            meta = {k: v for k, v in combined.items() if v is not None and v != ""}

            pages[page_num] = {
                "id": item.id,
                "url": item.url,
                "title": td["cleanTitle"],
                "content": td["content"],
                "wordCount": td["wordCount"],
                "date": item.date,
                "filters": filters,
                "meta": meta,
                "sortable": item_sortable,
                "hash": hashlib.sha256(td["content"].encode("utf-8")).hexdigest(),
            }

            self._index_tokens(index, td["titleTokens"], page_num, TITLE_WEIGHT)
            self._index_tokens(index, td["bodyTokens"], page_num, BODY_WEIGHT)
            self._index_tokens(index, td["urlTokens"], page_num, BODY_WEIGHT)

            page_num += 1

        return {"index": index, "pages": pages}

    @staticmethod
    def _reindex(tokens, start_index: int = 0):
        reindexed = []
        word_index = start_index
        for token in tokens:
            reindexed.append(Token(token.stem, token.original, word_index))
            word_index += 1
        return reindexed, word_index

    def _index_tokens(self, index: dict, tokens, page_num: int, weight: int) -> None:
        for token in tokens:
            stemmed = self.stemmer.stem(token.stem)
            position = token.position

            entry = index.setdefault(stemmed, {})
            page_entry = entry.get(page_num)
            if page_entry is None:
                page_entry = {"positions": {}, "meta_positions": []}
                entry[page_num] = page_entry

            if weight == TITLE_WEIGHT:
                page_entry["meta_positions"].append(position)
            else:
                bucket = page_entry["positions"].setdefault(weight, [])
                if len(bucket) < MAX_POSITIONS_PER_WEIGHT:
                    bucket.append(position)

            if token.stem != token.original:
                variants = entry.setdefault("_variants", {})
                vp = variants.setdefault(token.original, [])
                if page_num not in vp:
                    vp.append(page_num)
