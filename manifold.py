#!/usr/bin/env python3

#-----------------------------------------------------------------------#
#
#    This program takes n-gram files and a word list    
#    and creates a file with lists of most similar words.
#    John Goldsmith and Wang Xiuli 2012.
#    Jackson Lee and Simon Jacobs 2014
#
#-----------------------------------------------------------------------#


import argparse
from pathlib import Path
from collections import OrderedDict

import networkx as nx

from manifold_module import (GetMyWords, GetContextArray,
                             Normalize, compute_incidence_graph,
                             compute_laplacian, GetEigenvectors,
                             compute_words_distance, compute_closest_neighbors,
                             GetMyGraph)
import ngrams

from lxa5lib import (get_language_corpus_datafolder, json_pdump,
                     changeFilenameSuffix, stdout_list,
                     load_config_for_command_line_help)


def makeArgParser(configfilename="config.json"):

    language, \
    corpus, \
    datafolder, \
    configtext = load_config_for_command_line_help(configfilename)

    parser = argparse.ArgumentParser(
        description="This program computes word neighbors.\n\n{}"
                    .format(configtext),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--config", help="configuration filename",
                        type=str, default=configfilename)

    parser.add_argument("--language", help="Language name",
                        type=str, default=None)
    parser.add_argument("--corpus", help="Corpus file to use",
                        type=str, default=None)
    parser.add_argument("--datafolder", help="path of the data folder",
                        type=str, default=None)

    parser.add_argument("--maxwordtypes", help="Number of word types to handle",
                        type=int, default=1000)
    parser.add_argument("--nNeighbors", help="Number of neighbors",
                        type=int, default=9)
    parser.add_argument("--nEigenvectors", help="Number of eigenvectors",
                        type=int, default=11)

    parser.add_argument("--wordtocontexts", help="create the WordToContexts dict?",
                        type=bool, default=True)
    parser.add_argument("--contexttowords", help="create the ContextToWords dict?",
                        type=bool, default=False)

    return parser


def main(language, corpus, datafolder,
         maxwordtypes, nNeighbors, nEigenvectors, 
         create_WordToContexts, create_ContextToWords):

    corpusStem = Path(corpus).stem
    corpusName = corpusStem + '_' + str(maxwordtypes) + '_' + str(nNeighbors)

    infolder = Path(datafolder, language, 'ngrams')
    outfolder = Path(datafolder, language, 'neighbors')
    outcontextsfolder = Path(datafolder, language, 'word_contexts')

    if not outfolder.exists():
        outfolder.mkdir(parents=True)

    if not outcontextsfolder.exists():
        outcontextsfolder.mkdir(parents=True)

    infileWordsname = Path(infolder, corpusStem + '_words.txt')
    infileBigramsname = Path(infolder, corpusStem + '_bigrams.txt')
    infileTrigramsname = Path(infolder, corpusStem + '_trigrams.txt')

    if not infileWordsname.exists():
        ngrams.main(language, corpus, datafolder)

    print('Reading word list...', flush=True)
    mywords = GetMyWords(infileWordsname, corpus)

    print("Word file is", infileWordsname, flush=True)
    print("Number of neighbors to find for each word type: ", nNeighbors)
    print('Corpus has', len(mywords), 'word types', flush=True)

    lenMywords = len(mywords)
    if lenMywords > maxwordtypes:
        nWordsForAnalysis = maxwordtypes
    else:
        nWordsForAnalysis = lenMywords
    print('number of words for analysis adjusted to', nWordsForAnalysis)

    analyzedwordlist = list(mywords.keys())[ : nWordsForAnalysis] 

    outfilenameNeighbors = Path(outfolder, corpusName + \
                                "_nearest_neighbors.txt")

    outfilenameNeighborGraph = Path(outfolder, corpusName + \
                                    "_nearest_neighbors.gexf")

    outWordToContexts_json = Path(outcontextsfolder, corpusName + \
                                       "_WordToContexts.json")

    outContextToWords_json = Path(outcontextsfolder, corpusName + \
                                       "_ContextToWords.json")

    print("Reading bigrams/trigrams and computing context array...", flush=True)

    context_array, WordToContexts, ContextToWords = GetContextArray(corpus, 
                                   maxwordtypes, analyzedwordlist,
                                   infileBigramsname, infileTrigramsname,
                                   create_WordToContexts, create_ContextToWords)

    if create_WordToContexts:
        json_pdump(WordToContexts, outWordToContexts_json.open("w"),
                   key=lambda x : len(x[1]), reverse=True)
        print('WordToContexts ready', flush=True)

    if create_ContextToWords:
        json_pdump(ContextToWords, outContextToWords_json.open("w"),
                   key=lambda x : len(x[1]), reverse=True)
        print('ContextToWords ready', flush=True)

    print("Computing shared contexts...", flush=True)
    CountOfSharedContexts = context_array.dot(context_array.T).todense()
    del context_array

    print("Computing diameter...", flush=True)
    Diameter = Normalize(maxwordtypes, CountOfSharedContexts)

    print("Computing incidence graph...", flush=True)
    incidencegraph = compute_incidence_graph(maxwordtypes, Diameter,
                                             CountOfSharedContexts)
    
    print("Computing mylaplacian...", flush=True)
    mylaplacian = compute_laplacian(maxwordtypes, Diameter, incidencegraph)
    del Diameter
    del incidencegraph

    print("Computing eigenvectors...", flush=True)
    myeigenvalues, myeigenvectors = GetEigenvectors(mylaplacian)
    del mylaplacian
    del myeigenvalues

    print('Computing distances between words...', flush=True)
    # take first N columns of eigenvector matrix
    coordinates = myeigenvectors[:,:nEigenvectors] 
    wordsdistance = compute_words_distance(maxwordtypes, coordinates)
    del coordinates

    print('Computing nearest neighbors now... ', flush=True)
    closestNeighbors = compute_closest_neighbors(analyzedwordlist,
                                                 wordsdistance, nNeighbors)

    WordToNeighbors = OrderedDict()
    for wordno in range(nWordsForAnalysis):
        line = closestNeighbors[wordno]
        word_idx, neighbors_idx = line[0], line[1:]
        word = analyzedwordlist[word_idx]
        neighbors = [analyzedwordlist[idx] for idx in neighbors_idx]
        WordToNeighbors[word] = neighbors

    with outfilenameNeighbors.open('w') as f:
        print("# language: {}\n# corpus: {}\n"
              "# Number of word types analyzed: {}\n"
              "# Number of neighbors: {}\n".format(language, corpus,
                                              maxwordtypes, nNeighbors), file=f)

        for word, neighbors in WordToNeighbors.items():
            print(word, " ".join(neighbors), file=f)

    neighbor_graph = GetMyGraph(outfilenameNeighbors)
    nx.write_gexf(neighbor_graph, str(outfilenameNeighborGraph))

    WordToNeighbors_json = changeFilenameSuffix(outfilenameNeighbors, ".json")
    json_pdump(WordToNeighbors, WordToNeighbors_json.open("w"), asis=True)

    outputfilelist = [outfilenameNeighbors, outfilenameNeighborGraph,
                      WordToNeighbors_json]

    if create_WordToContexts:
        outputfilelist.append(outWordToContexts_json)
    if create_ContextToWords:
        outputfilelist.append(outContextToWords_json)

    stdout_list("Output files:", *outputfilelist)


if __name__ == "__main__":

    args = makeArgParser().parse_args()
    
    maxwordtypes = args.maxwordtypes
    nNeighbors = args.nNeighbors
    nEigenvectors = args.nEigenvectors
    create_WordToContexts = args.wordtocontexts
    create_ContextToWords = args.contexttowords

    description="You are running {}.\n".format(__file__) + \
                "This program computes word neighbors.\n" + \
                "maxwordtypes = {}\n".format(maxwordtypes) + \
                "nNeighbors = {}\n".format(nNeighbors) + \
                "nEigenvectors = {}\n".format(nEigenvectors) + \
                "create_WordToContexts = {}\n".format(create_WordToContexts) + \
                "create_ContextToWords = {}\n".format(create_ContextToWords)

    language, corpus, datafolder = get_language_corpus_datafolder(args.language,
                                      args.corpus, args.datafolder, args.config,
                                      description=description,
                                      scriptname=__file__)

    main(language, corpus, datafolder,
         maxwordtypes, nNeighbors, nEigenvectors,
         create_WordToContexts, create_ContextToWords)

