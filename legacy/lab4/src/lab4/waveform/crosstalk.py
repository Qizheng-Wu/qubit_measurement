import numpy as np


def corr_xtalk(xtalk: np.ndarray, xtalk_space: list[str], **vec_out):
    """Returns input bias to implement given output in presence of crosstalk.

    Args:
        xtalk: crosstalk matrix like [
                [1, q1_by_z2, q1_by_z3],
                [q2_by_z1, 1, q3_by_z1],
                [q3_by_z1, q3_by_z2, 1],
            ]
        xtalk_space: qubit labels like ['Q1', 'Q2', 'Q3'] for xtalk above.
        vec_out: key-value pairs like "qubit=desired_bias".
            qubits out of xtalk_space are ignored.

    Returns:
        dict(qubit=bias) for all qubits given in vec_out.

    Example:
        >>> corr_xtalk(
                xtalk=[[1,0,7], [0.1,1,7], [7,7,1]],
                xtalk_space=['Q1', 'Q2', 'Q3'],
                Q1=1,
                Q2=0,
                Q5=5,
            )
        {'Q1': 1.0, 'Q2': -0.1, 'Q5': 5}

        >>> corr_xtalk(
                xtalk=[[1,0,7], [0.1,1,7], [7,7,1]],
                xtalk_space=['Q1', 'Q2', 'Q3'],
                Q1=[1,1],
                Q2=[0,0],
                Q5=[5,5],
            )
        {'Q1': array([1., 1.]), 'Q2': array([-0.1, -0.1]), 'Q5': [5, 5]}
    """
    sub_space = [k for k in vec_out.keys() if k in xtalk_space]
    sub_idx = [xtalk_space.index(qb) for qb in sub_space]
    sub_xtalk = np.asarray(xtalk)[np.ix_(sub_idx, sub_idx)]
    sub_xinv = np.linalg.inv(sub_xtalk)
    sub_vec_out = np.asarray([vec_out[qb] for qb in sub_space])
    sub_vec_in = sub_xinv @ sub_vec_out

    vec_in = vec_out.copy()
    for k, v in zip(sub_space, sub_vec_in):
        vec_in[k] = v
    return vec_in
