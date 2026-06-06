<?php
declare(strict_types=1);
require __DIR__ . '/../../scolta-php/vendor/autoload.php';

use Tag1\Scolta\Html\HtmlCleaner;
use Tag1\Scolta\Index\Tokenizer;

$tok = new Tokenizer();

function dump(Tokenizer $tok, string $text, int $start = 0): array
{
    $out = [];
    foreach ($tok->tokenize($text, $start) as $t) {
        $out[] = [$t->stem, $t->original, $t->position];
    }
    return $out;
}

$cases = [
    'basic' => ['Hello World', 0],
    'diacritic' => ['café', 0],
    'hyphen' => ['mother-in-law', 0],
    'camel' => ['myPage', 0],
    'camel_multi' => ['myPageTitle parseHTMLString', 0],
    'numbers' => ['123abc 4.5 v2', 0],
    'position' => ['hello world', 0],
    'start_offset' => ['hello', 100],
    'punctuation' => ['hello, world! (yes) -- "quote"', 0],
    'multi_space' => ['hello   world', 0],
    'unicode_lower' => ['ÜBER STRASSE Élan', 0],
    'cjk4' => ['你好世界', 0],
    'mixed_cjk' => ['Hello人工智能World', 0],
    'hiragana' => ['おはよう', 0],
    'katakana' => ['コンピュータ', 0],
    'korean' => ['안녕하세요', 0],
    'single_cjk' => ['猫', 0],
    'two_cjk' => ['日本', 0],
    'cyrillic' => ['физика квантовая', 0],
    'contractions' => ["don't it's we've o'clock", 0],
    'emoji' => ['hello 😀 world 🎉 done', 0],
    'diacritics_mix' => ['Café résumé naïve Zürich jalapeño piñata', 0],
    'hyphen_short_seg' => ['a-b-cd e-fghi', 0],
    'mixed_all' => ['Hello café 123 mother-in-law myPage 你好', 0],
    'german_sharp_s' => ['Straße GROSSE Fußball', 0],
    'apostrophe_unicode' => ["l'été coeur", 0],
];

$out = ['tokenizer_cases' => []];
foreach ($cases as $name => [$text, $start]) {
    $out['tokenizer_cases'][$name] = [
        'input' => $text,
        'start' => $start,
        'tokens' => dump($tok, $text, $start),
    ];
}

// Real prose: cleaned text of the first few recipe fixtures (exercises the
// tokenizer on the same content the indexer sees).
$recipeDir = __DIR__ . '/../tests/fixtures/recipes';
foreach (['01-eggplant-parmigiana.html', '05-dan-dan-noodles.html', '16-persian-jeweled-rice.html'] as $f) {
    $html = file_get_contents($recipeDir . '/' . $f);
    $clean = HtmlCleaner::clean($html);
    $out['tokenizer_cases']['recipe:' . $f] = [
        'input' => $clean,
        'start' => 0,
        'tokens' => dump($tok, $clean, 0),
    ];
}

file_put_contents(
    __DIR__ . '/../tests/fixtures/tokenizer_parity.json',
    json_encode($out, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
);
echo 'wrote tokenizer golden: ' . count($out['tokenizer_cases']) . " cases\n";
