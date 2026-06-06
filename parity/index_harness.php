<?php
declare(strict_types=1);
$base = __DIR__ . '/../../scolta-php';
require $base . '/vendor/autoload.php';
require $base . '/tests/Support/CborDecoder.php';

use Tag1\Scolta\Export\ContentItem;
use Tag1\Scolta\Index\{InvertedIndexBuilder, Tokenizer, Stemmer, CborEncoder,
    PagefindFormatWriter, StreamingFormatWriter};
use Tag1\Scolta\Tests\Support\CborDecoder;

function recipe_items(string $base): array {
    $items = [];
    foreach (glob($base . '/tests/fixtures/recipes/*.html') as $i => $p) {
        $html = file_get_contents($p);
        preg_match('/<title>(.*?)<\/title>/s', $html, $m); $title = $m[1] ?? '';
        preg_match('/data-pagefind-meta="url:([^"]*)"/', $html, $mu); $url = $mu[1] ?? ('/r/' . $i);
        $items[] = new ContentItem((string)($i + 1), $title, $html, $url, '2024-01-01', 'Recipes', 'en');
    }
    return $items;
}

function rmrf(string $dir): void {
    if (!is_dir($dir)) return;
    $it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($dir, FilesystemIterator::SKIP_DOTS), RecursiveIteratorIterator::CHILD_FIRST);
    foreach ($it as $f) { $f->isDir() ? rmdir($f->getRealPath()) : unlink($f->getRealPath()); }
    rmdir($dir);
}

$ASSET_FILES = ['pagefind.js', 'pagefind-worker.js', 'wasm.en.pagefind', 'wasm.unknown.pagefind'];

/** Decode a build dir to a canonical, order-independent structure. */
function decode_structure(string $buildDir): array {
    // Words across all index chunks.
    $words = [];
    foreach (glob($buildDir . '/index/*.pf_index') as $f) {
        $chunk = CborDecoder::decodePfFile($f); // [[ [word, pages, variants], ... ]]
        foreach ($chunk[0] as $entry) {
            [$word, $pages, $variants] = $entry;
            $words[$word] = ['pages' => $pages, 'variants' => $variants];
        }
    }
    ksort($words);

    // Fragments keyed by url.
    $fragments = [];
    foreach (glob($buildDir . '/fragment/*.pf_fragment') as $f) {
        $raw = gzdecode(file_get_contents($f));
        if (str_starts_with($raw, 'pagefind_dcd')) $raw = substr($raw, 12);
        $j = json_decode($raw, true);
        $fragments[$j['url']] = $j;
    }
    ksort($fragments);

    // Filters keyed by name.
    $filters = [];
    foreach (glob($buildDir . '/filter/*.pf_filter') as $f) {
        $d = CborDecoder::decodePfFile($f); // [name, [[value,[pages]], ...]]
        $name = $d[0]; $vals = [];
        foreach ($d[1] as [$value, $pages]) { sort($pages); $vals[$value] = $pages; }
        ksort($vals);
        $filters[$name] = $vals;
    }
    ksort($filters);

    // pf_meta.
    $metaFile = glob($buildDir . '/pagefind.*.pf_meta')[0];
    $meta = CborDecoder::decodePfFile($metaFile); // [version, pages, chunks, filters, sorts, metaFields]
    $sorts = [];
    foreach ($meta[4] as [$field, $indices]) { $sorts[$field] = $indices; }
    $metaOut = [
        'version' => $meta[0],
        'pages' => $meta[1],            // list of [fragmentHash, wordCount]
        'sorts' => $sorts,
        'metaFields' => $meta[5],
        'pageCount' => count($meta[1]),
        'chunkCount' => count($meta[2]),
    ];

    $entry = json_decode(file_get_contents($buildDir . '/pagefind-entry.json'), true);

    return ['words' => $words, 'fragments' => $fragments, 'filters' => $filters, 'meta' => $metaOut, 'entry' => $entry];
}

$out = [];

// --- Recipe corpus: streaming + buffered, structural ---
$items = recipe_items($base);
$builder = new InvertedIndexBuilder(new Tokenizer(), new Stemmer('en'));
$built = $builder->build($items);

$dirS = sys_get_temp_dir() . '/scolta-parity-stream';
rmrf($dirS);
$cbor = new CborEncoder();
$ws = new StreamingFormatWriter($cbor);
$ws->beginWrite($dirS);
ksort($built['pages']);
foreach ($built['pages'] as $pn => $pd) { $ws->writePage($pn, $pd); }
$words = array_map('strval', array_keys($built['index']));
sort($words);
foreach ($words as $w) { $ws->writeTerm($w, $built['index'][$w]); }
$ws->endWrite();
$out['recipes_streaming'] = decode_structure($dirS . '/.scolta-building');

$dirB = sys_get_temp_dir() . '/scolta-parity-buffered';
rmrf($dirB);
(new PagefindFormatWriter($cbor))->write($built['index'], $built['pages'], $dirB);
$out['recipes_buffered'] = decode_structure($dirB . '/.scolta-building');

// The PHP-built index+pages, so the Python test can drive the Python writers
// with an identical index (isolating the format writer from the stemmer, which
// has a known wamania-vs-canonical divergence documented in the Python tests).
$out['php_built'] = ['index' => $built['index'], 'pages' => $built['pages']];

// --- Controlled alphabetic-only corpus: byte-exact ---
$ctrl = [
    new ContentItem('a', 'Chocolate Cake Recipe', '<p>This delightful chocolate cake recipe uses cocoa butter and vanilla. The café serves résumé pastries. A truly wonderful dessert for everyone to enjoy.</p>', '/recipes/chocolate-cake', '2024-03-01', 'Bakery', 'en', ['cuisine' => 'french'], [], ['rating' => 'four']),
    new ContentItem('b', 'Vanilla Bean Custard', '<p>Smooth vanilla bean custard with mother-in-law approval and a parseHTML helper note. Creamy and rich pudding dessert.</p>', '/recipes/vanilla-custard', '2024-05-15', 'Bakery', 'en', ['cuisine' => 'italian'], [], ['rating' => 'five']),
    new ContentItem('c', 'Apple Pie Classic', '<p>Classic apple pie with cinnamon and nutmeg. Grandmother recipe passed through generations. Warm comforting autumn dessert.</p>', '/recipes/apple-pie', '2023-11-20', 'Bakery', 'en', ['cuisine' => 'american'], [], ['rating' => 'four']),
];
$builtC = $builder->build($ctrl);
$dirC = sys_get_temp_dir() . '/scolta-parity-ctrl';
rmrf($dirC);
$wc = new StreamingFormatWriter($cbor);
$wc->beginWrite($dirC);
ksort($builtC['pages']);
foreach ($builtC['pages'] as $pn => $pd) { $wc->writePage($pn, $pd); }
$wordsC = array_map('strval', array_keys($builtC['index']));
sort($wordsC);
foreach ($wordsC as $w) { $wc->writeTerm($w, $builtC['index'][$w]); }
$wc->endWrite();

$cb = $dirC . '/.scolta-building';
$payloads = [];
$it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($cb, FilesystemIterator::SKIP_DOTS));
foreach ($it as $f) {
    if (!$f->isFile()) continue;
    $rel = substr($f->getPathname(), strlen($cb) + 1);
    $name = $f->getFilename();
    if (in_array($name, $ASSET_FILES, true)) continue;
    if ($name === 'pagefind-entry.json') continue;
    $raw = gzdecode(file_get_contents($f->getPathname()));
    if (str_starts_with($raw, 'pagefind_dcd')) $raw = substr($raw, 12);
    $payloads[$rel] = bin2hex($raw);
}
ksort($payloads);
$out['controlled_streaming'] = [
    'payloads' => $payloads,
    'entry' => json_decode(file_get_contents($cb . '/pagefind-entry.json'), true),
    'items' => array_map(fn ($i) => [
        'id' => $i->id, 'title' => $i->title, 'body_html' => $i->bodyHtml, 'url' => $i->url,
        'date' => $i->date, 'site_name' => $i->siteName, 'language' => $i->language,
        'filters' => $i->filters, 'metadata' => $i->metadata, 'sortable' => $i->sortable,
    ], $ctrl),
];

file_put_contents(__DIR__ . '/../tests/fixtures/index_parity.json',
    json_encode($out, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
echo 'wrote index golden: recipes vocab=' . count($out['recipes_streaming']['words'])
    . ' controlled payloads=' . count($payloads) . "\n";
