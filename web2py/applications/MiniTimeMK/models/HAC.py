import collections
import heapq
import math
import re
import time


def millis():
    """
    :return: A millisecond approximation of the current time
    """

    return int(round(time.time() * 1000))


def get_all_posts(days_ago=2):
    """
    Get all posts from the database.

    :return: List containing (post_id, post_text) tuples
    """
    import datetime
    now = datetime.datetime.now()
    dates = set([])
    if days_ago is not None and days_ago > 0:
        dates = set([(now - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_ago+1)])

    delta_rows = []
    all_rows = []
    # Very important not to have duplicates in the select !
    # TODO: Get only posts from the last 2 days
    for row in db().select(db.posts.ALL, orderby=~db.posts.pubdate):
        text = row.text
        text = re.sub('\n', ' ', text)
        text = re.sub('\s+', ' ', text)
        all_rows.append((row.id, text.strip()))

        if row.pubdate.strftime("%Y-%m-%d") in dates:
            delta_rows.append((row.id, text.strip()))
            # print row.id, row.pubdate

    return delta_rows, all_rows


def heap_remove_at_index(heap, idx):
    """
    Removes the element at index idx in heap with O(logN) complexity.

    :param heap: The heap from which the element should be removed
    :param idx: The index at which the element should be removed
    :return: The value of the removed element
    """
    if idx == len(heap)-1:
        return heap.pop()

    result = heap[idx]
    heap[idx] = heap.pop()
    heapq._siftup(heap, idx)
    return result


def heap_remove_element(heap, element):
    """
    Removes the given element from the heap while preserving the structure. Done in O(logN) time.

    :param heap: A list which represents a heap
    :param element: The element to be removed
    """
    index = heap.index(element * (-1))
    heap_remove_at_index(heap, index)


def tf_idf(tf_dict, idf_dict, doc_id, document, all_docs_splitted, terms_set=None):
    """
    Calculates the top 12 tf-idf keywords of a document.

    :param document: The document whose tf-idf should be calculated, represented as a string list
    :param all_docs_splitted: A list of the documents' words represented as string lists
    :param terms_set: An optional set of terms for which to calculate tf_idf
        If None, tf_idf is calculated for every word in the document
    :return: A dictionary of the 12 tf-idf keywords and their weights,
        or an empty dictionary if there aren't 12 keywords
    """

    # We use a set of the documents terms because we already have the counts
    # Drops down 300 ms on 2600 posts
    terms = set(document) if terms_set is None else terms_set
    tokens = {}
    for term in terms:
        tf = (1.0 * tf_dict[doc_id].get(term, 0) / len(document))
        idf = math.log(1.0 * len(all_docs_splitted) / (len(idf_dict.get(term, [])) + 1))

        weight = tf*idf
        tokens[term] = weight

    sorted_tokens = sorted(tokens.items(), key=lambda x: (x[1], x[0]), reverse=True)

    ret = collections.defaultdict(lambda: 0)
    if len(sorted_tokens) >= 12:
        for j in range(12):
            term = sorted_tokens[j][0]
            weight = sorted_tokens[j][1]

            ret[term] = weight
    return ret


def cosine_similarity(d1, d2):
    """
    Calculates cosine similarity between two tf-idf vectors.

    :param d1: Vector 1
    :param d2: Vector 2
    :return: The cosine similarity between vectors d1 and d2
    """

    upper_sum = 0
    for n in d1:
        if n in d2:
            upper_sum = upper_sum + d1[n]*d2[n]

    if upper_sum == 0:  # If upper_sum = 0, no need to calculate the lower sums
        return 0

    normalization_sum1 = 0.0
    normalization_sum2 = 0.0

    for br in d1.values():
        normalization_sum1 += br*br

    for br in d2.values():
        normalization_sum2 += br*br

    normalization_sum1 = math.sqrt(normalization_sum1)
    normalization_sum2 = math.sqrt(normalization_sum2)

    # upper_sum / (normalization_sum1 * normalization_sum2)
    return 1.0 * upper_sum / (normalization_sum1 * normalization_sum2)


def init_fill_heap(vectors, score_pair, reverse_score_pair, heap, threshold):
    """
    Initial calculation of similarity for each pair of tf-idf vectors.

    :param vectors: A list of the tf-idf vectors for the documents
    :param score_pair: An empty dictionary to be filled with score -> [(pair_i, pair_j), ...] pairs
    :param reverse_score_pair: A reverse dictionary of score_pair to be filled with (pair_i, pair_j) -> score pairs
    :param heap: An empty list to be used as a heap
    :param threshold A decimal threshold above which clusters are merged
    :return: Fills score_pair, reverse_score_pair and heap with the corresponding data
    """

    n = len(vectors)
    for i in range(n):
        for j in range(i + 1, n):
            d1 = vectors[i]
            d2 = vectors[j]
            score = cosine_similarity(d1, d2)

            if score > 1.0:
                score = 1.0

            if score > threshold:
                # print score, " : ", (i, j)

                score_pair[score] = score_pair.get(score, [])
                score_pair[score].append((i, j))

                # TODO: (i, j) -> float pair, instead of list
                reverse_score_pair[(i, j)] = reverse_score_pair.get((i, j), []) + [score]
                heapq.heappush(heap, score*(-1))


def get_most_similar(score_pair, reverse_score_pair, heap):
    """
    Return the largest value for similarity between two vectors.

    :param score_pair: A dictionary containing score : pair key-value pairs
    :param reverse_score_pair: A reverse dictionary of score_pair containing pair : score key-value pairs
    :param heap: The heap of similarity scores
    :return: The i and j index of the pair that is most similar
    """
    max_score = heapq.heappop(heap) * (-1)
    (result_i, result_j) = score_pair[max_score].pop()
    del reverse_score_pair[(result_i, result_j)]

    # Remove scores of every non-optimal pair which has result_i in it
    all_pairs_i = [(i, j) for (i, j) in reverse_score_pair if i == result_i or j == result_i]
    for (i, j) in all_pairs_i:
        if reverse_score_pair[(i, j)]:
            score = reverse_score_pair[(i, j)].pop()
            heap_remove_element(heap, score)
            score_pair[score].remove((i, j))
        else:
            del reverse_score_pair[(i, j)]

    # Remove scores of every non-optimal pair which has result_j in it
    all_pairs_j = [(i, j) for (i, j) in reverse_score_pair if i == result_j or j == result_j]
    for (i, j) in all_pairs_j:
        if reverse_score_pair[(i, j)]:
            score = reverse_score_pair[(i, j)].pop()
            heap_remove_element(heap, score)
            score_pair[score].remove((i, j))
        else:
            del reverse_score_pair[(i, j)]

    return result_i, result_j


def merge_texts(tf_dict, idf_dict, i, j, vectors, all_docs_splitted, recent_docs_splitted, offset):
    """
    Merges the string contents of two documents, and calculates the top 12 keywords.

    :param doc1: A list containing the words of the first document
    :param doc2: A list containing the words of the second document
    :param all_docs_splitted: A list containing the words of all documents
    :return: The top 12 tf-idf keywords of the merged document
        and the index at which the merged text was inserted
    """

    doc_i = all_docs_splitted[i]
    vec_i = vectors[i]

    doc_j = all_docs_splitted[j]
    vec_j = vectors[j]

    result = doc_i + doc_j
    recent_docs_splitted.append(result)
    all_docs_splitted.append(result)

    merge_id = len(recent_docs_splitted) - 1

    tf_dict[merge_id + offset] = {}
    for term in result:
        tf_dict[merge_id + offset][term] = tf_dict[merge_id + offset].get(term, 0) + 1
        # TODO: idf shouldn't be changed ?
        # idf_dict[term] = idf_dict.get(term, set([]))
        # idf_dict[term].add(merge_id + offset)

    max_set = set([])
    max_set.update(vec_i.keys())
    max_set.update(vec_j.keys())

    ret = tf_idf(tf_dict, idf_dict, merge_id + offset, result, all_docs_splitted, max_set)
    return merge_id, ret


def hac(tf_dict, idf_dict, heap, vectors, score_pair, reverse_score_pair,
        all_docs_splitted, recent_docs_splitted, vector_id_map, threshold, offset):
    """
    Performs Hierarchical Agglomerative Clustering on the given posts.

    :param heap: A heap containing cosine similarities between the posts
    :param vectors: A list containing the 12 tf-idf keywords of the posts
    :param score_pair: A dictionary containing score : pair key-value pairs
    :param reverse_score_pair: A reverse dictionary of score_pair (simVec) containing pair : score key-value pairs
    :param all_docs_splitted: A list of the words of each post
    :param vector_id_map
    :param threshold A decimal threshold above which clusters are merged
    :return: A dictionary containing cluster_id -> (id, id) pairs
    """
    hash_merged = {}
    k = len(vectors)
    deleted = set([])

    while heap:
        result_i, result_j = get_most_similar(score_pair, reverse_score_pair, heap)
        deleted.add(result_i)
        deleted.add(result_j)

        merge_id, merged_vector = merge_texts(tf_dict, idf_dict, result_i, result_j,
                                              vectors, all_docs_splitted, recent_docs_splitted, offset)
        vectors.append(merged_vector)
        vector_id_map[len(vectors) - 1] = merge_id

        for i in range(len(vectors) - 1):
            if i not in deleted:
                d1 = vectors[i]
                score = cosine_similarity(d1, merged_vector)

                if k != merge_id:
                    print "k != merge_id", k, merge_id, merge_id - offset

                if score > 1.0:
                    print 'Score bigger than 1: %f' % score
                    score = 1.0

                if score > threshold:
                    # print score, " : ", i, " ", K
                    score_pair[score] = score_pair.get(score, [])
                    score_pair[score].append((i, k))

                    # TODO: (i, k) -> float pair, instead of list
                    reverse_score_pair[(i, k)] = reverse_score_pair.get((i, k), []) + [score]
                    heapq.heappush(heap, score*(-1))

        k += 1
        hash_merged[merge_id] = (result_i, result_j)
    return hash_merged


def get_children_clusters(result_dict, key, eliminated):
    ret = []
    eliminated.add(key)
    if result_dict.get(key, None) is None:
        ret.append(key)
    else:
        for c_id in result_dict[key]:
            if c_id not in eliminated:
                # eliminated.add(c_id)
                ret += get_children_clusters(result_dict, c_id, eliminated)
    return ret


def clustering():
    """
    Main clustering function.

    :return: A list of (cluster_id, cluster_score, master_id, cluster_category, cluster_posts)
        sorted by cluster_score
    """

    tc1 = millis()
    recent_docs, all_docs = get_all_posts()  # A list of (post_id, text) tuples
    all_docs_splitted = []  # A list of the words of each post
    recent_docs_splitted = []
    vectors = []    # A list for the tf-idf vector of each post
    score_pair = {}     # A dictionary with score -> [(pair_i, pair_j), ...]
    reverse_score_pair = {}     # A dictionary with (pair_i, pair_j) -> score
    heap = []       # A list to be used as heap
    vector_to_post_id = {}  # A helper dictionary for mapping between relative vector indexes and post_id
    docs_to_post_id = {}    # A helper dictionary for mapping between relative all_docs_splitted indexes and post_id

    limit = len(all_docs)  # 600
    threshold = 0.421

    print 'Posts splitting started'
    t1 = millis()
    idx = 0
    for (post_id, post_text) in all_docs[:limit]:
        post_words = post_text.split(' ')
        all_docs_splitted.append(post_words)

        docs_to_post_id[len(all_docs_splitted) - 1] = post_id

        idx += 1
    t2 = millis()

    idx = 0
    for (post_id, post_text) in recent_docs:
        post_words = post_text.split(' ')
        recent_docs_splitted.append(post_words)

        # print "Vector idx: ", idx, \
        #       "Post id: ", post_id, \
        #       " : ", " ".join(post_words)
        idx += 1
    print len(all_docs_splitted), 'posts splitted in ', (t2 - t1), ' ms'

    print 'tf-idf started'
    t1 = millis()
    tf_dict = {}
    idf_dict = {}

    # To use all posts: recent_docs_splitted = [a for a in all_docs_splitted]
    recent_len = len(recent_docs_splitted)
    offset = len(all_docs_splitted)

    for i, doc_words in enumerate(all_docs_splitted):
        doc_id = i  # docs_to_post_id[i]
        if doc_id >= 0 and doc_id < recent_len:
            doc_id += offset

        if tf_dict.get(doc_id, -1) != -1:
            print "ERROR, not empty initial"

        tf_dict[doc_id] = {}
        for term in doc_words:
            tf_dict[doc_id][term] = tf_dict[doc_id].get(term, 0) + 1
            idf_dict[term] = idf_dict.get(term, set([]))
            idf_dict[term].add(doc_id)
    t2 = millis()
    print "tf-idf dictionaries created in %d ms" % (t2 - t1)

    for i in range(len(recent_docs_splitted)):
        ret = tf_idf(tf_dict, idf_dict, i + offset, recent_docs_splitted[i], all_docs_splitted)
        vectors.append(ret)
        vector_to_post_id[len(vectors) - 1] = docs_to_post_id[i]
    t2 = millis()
    print 'tf-idf finished in %d ms (with dict creation included)' % (t2 - t1)

    print 'Initial heap filling started'
    t1 = millis()
    init_fill_heap(vectors, score_pair, reverse_score_pair, heap, threshold)
    t2 = millis()
    print 'Heap initially filled in %d ms' % (t2 - t1)

    print 'HAC started'
    t1 = millis()
    result = hac(tf_dict, idf_dict, heap, vectors, score_pair, reverse_score_pair,
                 all_docs_splitted, recent_docs_splitted, vector_to_post_id, threshold, offset)
    t2 = millis()
    print 'HAC finished in %d ms' % (t2 - t1)

    # Creating a cluster-id -> [posts] dictionary
    eliminated = set([])
    final_dict = {}
    for key in sorted(result, reverse=True):
        post_ids = []
        eliminated.add(key)
        for c_id in result[key]:
            if c_id not in eliminated:
                post_ids += get_children_clusters(result, c_id, eliminated)
        if post_ids:    # Skip empty arrays
            final_dict[key] = post_ids
        # print key, ' ', result[key]

    print 'Inserting clusters into database'
    t1 = millis()
    last_id = -1
    result = {}

    # Empty cluster table and reset id
    db(db.cluster).delete()
    db.executesql("ALTER TABLE cluster AUTO_INCREMENT=1")
    db.commit()

    for key in sorted(final_dict, reverse=True):
        cluster_posts = []
        cluster_categories = {}
        min_epoch = time.time()
        master_id = -1

        for it in final_dict[key]:  # final_dict[key] is a list of post_ids
            post_id = int(vector_to_post_id[it])
            cluster_posts.append(post_id)

            post_row = db.posts[post_id]
            post_category = int(post_row.category)

            # Count number of posts for each category
            cluster_categories[post_category] = cluster_categories.get(post_category, 0) + 1

            if post_row.pubdate is not None:
                post_date = post_row.pubdate.timetuple()
            else:
                print "Datetime error occurred on post: ", post_id
                post_date = time.localtime()

            post_epoch = time.mktime(post_date)
            if post_epoch < min_epoch:  # The master-post is the oldest in the cluster
                min_epoch = post_epoch
                master_id = post_id

        # Calculate cluster category
        # Sort by value, and get first 2, then multiply by factor
        sorted_categories = sorted(cluster_categories.items(), key=lambda x: x[1], reverse=True)
        max_categories = sorted_categories[:min(2, len(sorted_categories))]
        max_factor = -1
        cluster_category = -1
        for category, num_posts in max_categories:
            factor = db.categories[category].factor * num_posts
            if factor > max_factor:
                max_factor = factor
                cluster_category = category

        if cluster_category == -1:  # DEBUG purpose
            print "ERROR: Cluster has no category or posts"

        # This gives the difference in seconds, a pretty big number.
        # Divided by 3600 to get hours, because 2 hours = 7200 seconds
        # and exp(-7200) ~ 0.0, and we need a valid metric for more than 2 hours
        # cluster_score = math.exp(-(current_time - min_epoch)/(60*60))*math.log(len(cluster_posts))

        # alpha e faktor moze da se menuva i spored nego kje se gleda kolku vlijae starosta
        alpha = 1
        time_now = time.time()
        sum_time = 0.0
        different_sources = set([])
        for post_id in cluster_posts:
            different_sources.add(db.posts[post_id].source)
            t = time.mktime(db.posts[post_id].pubdate.timetuple())
            c = math.exp(alpha * (- abs(time_now - t) / (60.0 * 60.0)))
            sum_time += c

        source_entropy = 1
        if len(cluster_posts) > 1:
            source_entropy = (len(different_sources)*1.0/len(cluster_posts)) + 1
        if len(different_sources) == 1:
            source_entropy = 1
        cluster_score = source_entropy * sum_time
        # print cluster_score

        # Insert cluster into database
        db.cluster.insert(score=cluster_score,
                          master_post=master_id,
                          category=cluster_category,
                          size=len(cluster_posts))
        if last_id == -1:   # Get next cluster_ids with one select
            last_id = db().select(db.cluster.ALL).last().id

        print last_id, ' : ',
        # Update cluster id
        for post_id in cluster_posts:
            db(db.posts.id == post_id).update(cluster=last_id)
            print post_id,
        print

        result[last_id] = (cluster_score, master_id, cluster_category, cluster_posts)
        last_id += 1

    t2 = millis()
    print 'Inserting clusters finished in %d ms' % (t2 - t1)

    tc2 = millis()
    print 'Total clustering time: %d ms' % (tc2 - tc1)

    # Return only the newly formed clusters, FOR DEBUG PURPOSES
    # x[1] is the value, x[1][0] is the first element of the value: cluster_score
    return sorted(result.items(), key=lambda x: x[1][0], reverse=True)
